# src/orchestrator/orchestrator.py
# RecurDefend Orchestrator
# - 입력 LCE → Recursive CoT → Tool Verify → Cross-Correction → 출력 LCE
# - 이벤트 로깅, 예외 래핑, 상태머신 제어
# Contracts: contracts/MODULE_IO.md, contracts/API.md

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

# (선택) Pydantic 스키마를 직접 쓰고 싶다면 아래 import를 사용:
# from src.service.schemas import AgentQueryRequest, AgentQueryResponseData

# --------- 인터페이스 (Protocol) 선언 ---------
class BaseLogger(Protocol):
    def event(
        self,
        qid: str,
        stage: str,
        decision: Optional[str] = None,
        score: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
        latency_ms: Optional[float] = None,
        **kwargs: Any,
    ) -> None: ...
    def start(self, qid: str) -> None: ...
    def end(self, qid: str) -> None: ...

class InputLCE(Protocol):
    def predict(self, x: Dict[str, Any]) -> Dict[str, Any]: ...

class OutputLCE(Protocol):
    def predict(self, text: str) -> Dict[str, Any]: ...

class CoTController(Protocol):
    def run(self, prompt: str, context_html: Optional[str] = None) -> Dict[str, Any]: ...
    def rollback_or_patch(self, call: Dict[str, Any], verifier_result: Dict[str, Any]) -> Dict[str, Any]: ...

class ToolVerifier(Protocol):
    def check(self, call: Dict[str, Any], user_ctx: Dict[str, Any]) -> Dict[str, Any]: ...

class Aligner(Protocol):
    def align(self, intent_in: Dict[str, Any], text_out: str, trace: List[Dict[str, Any]]) -> Dict[str, Any]: ...

class IntentParser(Protocol):
    def parse(self, text: str) -> Dict[str, Any]: ...

class ConfigProvider(Protocol):
    def get(self, path: str, default: Any = None) -> Any: ...


# --------- 요청/응답 데이터클래스 ---------
@dataclass
class OrchestratorRequest:
    id: str
    user_text: str
    context_html: Optional[str]
    tools_allowed: List[str]
    opts: Dict[str, Any]

@dataclass
class OrchestratorResponse:
    id: str
    status: str            # "ok" | "blocked" | "repaired"
    answer: Optional[str]
    meta: Dict[str, Any]


# --------- 유틸 ---------
def _now_ms() -> float:
    return time.perf_counter() * 1000.0

def _elapsed_ms(start_ms: float) -> float:
    return max(0.0, _now_ms() - start_ms)

def _extract_tool_calls(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    calls = []
    for step in trace or []:
        tc = step.get("tool_call")
        if tc:
            calls.append(tc)
    return calls


# --------- Orchestrator 구현 ---------
class Orchestrator:
    def __init__(
        self,
        *,
        input_lce: InputLCE,
        cot_controller: CoTController,
        tool_verifier: ToolVerifier,
        aligner: Aligner,
        output_lce: OutputLCE,
        intent_parser: IntentParser,
        logger: BaseLogger,
        config: ConfigProvider,
    ) -> None:
        self.input_lce = input_lce
        self.cot = cot_controller
        self.toolv = tool_verifier
        self.aligner = aligner
        self.output_lce = output_lce
        self.intent_parser = intent_parser
        self.log = logger
        self.cfg = config

    # 메인 엔트리
    def process(self, req: OrchestratorRequest) -> OrchestratorResponse:
        qid = req.id
        self.log.start(qid)
        t0 = _now_ms()

        try:
            # 1) 입력 LCE
            s = _now_ms()
            in_res = self.input_lce.predict({"text": req.user_text, "html": req.context_html})
            self.log.event(
                qid=qid,
                stage="input_lce",
                decision="pass" if in_res.get("label") == "safe" else "deny",
                score=float(in_res.get("score")) if in_res.get("score") is not None else None,
                payload={"signals": in_res.get("signals", {})},
                latency_ms=_elapsed_ms(s),
            )
            if in_res.get("label") != "safe":
                return self._deny(req, reason="IPI suspected", t0=t0)

            # 2) Recursive CoT
            s = _now_ms()
            cot_out = self.cot.run(req.user_text, context_html=req.context_html)
            rolled_back = bool(cot_out.get("rolled_back", False))
            trace = cot_out.get("trace", [])
            self.log.event(
                qid=qid,
                stage="recursive_cot_step",
                decision="rollback" if rolled_back else "pass",
                payload={"rolled_back": rolled_back},
                latency_ms=_elapsed_ms(s),
            )

            # 2-1) Tool Verify (trace 내 tool_call 검사)
            tool_calls = _extract_tool_calls(trace)
            for call in tool_calls:
                s = _now_ms()
                # 사용자 컨텍스트 구성 (필요 시 외부에서 전달받아 확장 가능)
                user_ctx = {
                    "allowed": req.tools_allowed,
                    "role": req.opts.get("role", "user"),
                    "caller": "agent_orchestrator",
                    "user_id": req.opts.get("user_id", "anon"),
                }
                vr = self.toolv.check(call, user_ctx)
                self.log.event(
                    qid=qid,
                    stage="tool_verify",
                    decision="allow" if vr.get("allow") else "deny",
                    payload={
                        "tool": call.get("name"),
                        "reason": vr.get("reason"),
                        "patched": bool(vr.get("patched_args")),
                    },
                    latency_ms=_elapsed_ms(s),
                )
                if not vr.get("allow", False):
                    # 정책: deny면 롤백 또는 패치 경로로 회귀
                    s2 = _now_ms()
                    cot_out = self.cot.rollback_or_patch(call, vr)
                    trace = cot_out.get("trace", trace)
                    rolled_back = True
                    self.log.event(
                        qid=qid,
                        stage="recursive_cot_step",
                        decision="rollback",
                        payload={"rolled_back": True, "reason": "tool_denied"},
                        latency_ms=_elapsed_ms(s2),
                    )
            final_text = cot_out.get("final_text", "")

            # 3) Cross-Correction (의도 정렬)
            s = _now_ms()
            intent_in = self.intent_parser.parse(req.user_text)
            align_res = self.aligner.align(intent_in, final_text, trace)
            status = align_res.get("status")  # "ok" | "repaired" | "abort"
            fixed_text = align_res.get("output", final_text)
            self.log.event(
                qid=qid,
                stage="cross_correction",
                decision="repair" if status == "repaired" else ("deny" if status == "abort" else "pass"),
                payload={"status": status},
                latency_ms=_elapsed_ms(s),
            )
            if status == "abort":
                return self._deny(req, reason="objective mismatch unresolved", t0=t0)

            # 4) 출력 LCE
            s = _now_ms()
            out_res = self.output_lce.predict(fixed_text)
            self.log.event(
                qid=qid,
                stage="output_lce",
                decision="allow" if out_res.get("label") == "safe" else "deny",
                score=float(out_res.get("score")) if out_res.get("score") is not None else None,
                payload={"signals": out_res.get("signals", {})},
                latency_ms=_elapsed_ms(s),
            )
            if out_res.get("label") != "safe":
                return self._deny(req, reason="policy/leakage risk", t0=t0)

            # OK or REPAIRED
            status_out = "repaired" if (rolled_back or status == "repaired") else "ok"
            resp = OrchestratorResponse(
                id=qid,
                status=status_out,
                answer=fixed_text,
                meta={
                    "rolled_back": rolled_back,
                    "events_uri": f"/v1/logs/{qid}",
                    "latency_ms": _elapsed_ms(t0),
                },
            )
            self.log.end(qid)
            return resp

        except Exception as e:
            # 에러를 로그로 남기고 안전 차단
            self.log.event(
                qid=qid,
                stage="output_lce",  # 마지막 단계로 표기(임의)
                decision=None,
                payload={"error": {"code": "E500", "message": str(e)}},
                latency_ms=_elapsed_ms(t0),
            )
            self.log.end(qid)
            return OrchestratorResponse(
                id=qid,
                status="blocked",
                answer=None,
                meta={
                    "reason": "internal_error",
                    "events_uri": f"/v1/logs/{qid}",
                    "latency_ms": _elapsed_ms(t0),
                },
            )

    # --------- 내부 헬퍼 ---------
    def _deny(self, req: OrchestratorRequest, *, reason: str, t0: float) -> OrchestratorResponse:
        resp = OrchestratorResponse(
            id=req.id,
            status="blocked",
            answer=None,
            meta={
                "reason": reason,
                "events_uri": f"/v1/logs/{req.id}",
                "latency_ms": _elapsed_ms(t0),
            },
        )
        self.log.end(req.id)
        return resp


# --------- 간단한 Mock/Stub (선택) ---------
class DictConfig(ConfigProvider):
    """configs/default.yaml을 파싱해 dict로 들고왔다고 가정하고 .get 제공"""
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self._cfg = cfg

    def get(self, path: str, default: Any = None) -> Any:
        cur: Any = self._cfg
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur
