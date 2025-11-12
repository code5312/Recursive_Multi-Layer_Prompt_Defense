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
            opts = req.opts or {}

            # === 플래그: opts 우선, 없으면 config 사용 ===
            enable_input_lce = bool(opts.get(
                "enable_input_lce",
                self.cfg.get("orchestrator.enable_input_lce", True),
            ))
            enable_recursive_cot = bool(opts.get(
                "enable_recursive_cot",
                self.cfg.get("orchestrator.enable_recursive_cot", True),
            ))
            enable_tool_verify = bool(opts.get(
                "enable_tool_verify",
                self.cfg.get("orchestrator.enable_tool_verify", True),
            ))
            enable_cross_correction = bool(opts.get(
                "enable_cross_correction",
                self.cfg.get("orchestrator.enable_cross_correction", True),
            ))
            enable_output_lce = bool(opts.get(
                "enable_output_lce",
                self.cfg.get("orchestrator.enable_output_lce", True),
            ))


            # =========================================================
            # 1) 입력 LCE (Input LCE)
            # =========================================================
            if enable_input_lce:
                s = _now_ms()
                # req.context_html은 IPI 공격 탐지 시 중요한 신호가 될 수 있음
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
                    return self._deny(req, reason="IPI suspected by Input LCE", t0=t0)
            else:
                self.log.event(qid=qid, stage="input_lce", decision="pass", payload={"skipped": True})

            # =========================================================
            # 2) Recursive CoT (Tool Call 포함한 LLM 추론)
            # =========================================================
            if enable_recursive_cot:
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
                final_text = cot_out.get("final_text", "") # LLM의 최종 응답
            else:
                cot_out = {"final_text": req.user_text, "trace": [], "rolled_back": False}
                final_text = req.user_text
                self.log.event(qid=qid, stage="recursive_cot_step", decision="pass", payload={"skipped": True})

            # =========================================================
            # 2-1) Tool Verify (Tool Call이 생성된 경우에만 실행)
            # =========================================================
            tool_calls = _extract_tool_calls(trace)
            if enable_tool_verify and tool_calls:
                
                for call in tool_calls:
                    s = _now_ms()
                    # 사용자 컨텍스트 구성
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
                        # 정책: deny면 롤백 또는 패치 경로로 회귀 (재귀적 수정 유도)
                        s2 = _now_ms()
                        cot_out = self.cot.rollback_or_patch(call, vr)
                        trace = cot_out.get("trace", trace)
                        final_text = cot_out.get("final_text", final_text) # 수정된 최종 텍스트 반영
                        rolled_back = True
                        self.log.event(
                            qid=qid,
                            stage="recursive_cot_step",
                            decision="rollback",
                            payload={"rolled_back": True, "reason": "tool_denied"},
                            latency_ms=_elapsed_ms(s2),
                        )
                        # tool verify에 의해 롤백이 발생하면 루프를 종료하고 Cross-Correction으로 이동
                        break 
                
                # 롤백이 발생했으면 cot_out에서 final_text를 다시 가져옴 (이미 위에서 반영됨)
                # final_text = cot_out.get("final_text", final_text) 

            elif not enable_tool_verify:
                self.log.event(qid=qid, stage="tool_verify", decision="allow", payload={"skipped": True})
            
            # =========================================================
            # 3) Cross-Correction (의도 정렬)
            # =========================================================
            fixed_text = final_text # CoT 결과 또는 입력 텍스트로 초기화
            
            if enable_cross_correction:
                s = _now_ms()
                # LLM이 생성한 final_text를 user_text의 의도와 비교
                intent_in = self.intent_parser.parse(req.user_text)
                align_res = self.aligner.align(intent_in, final_text, trace)
                status = align_res.get("status")  # "ok" | "repaired" | "abort"
                fixed_text = align_res.get("output", final_text) # 수정된 텍스트 반영
                
                self.log.event(
                    qid=qid,
                    stage="cross_correction",
                    decision="repair" if status == "repaired" else ("deny" if status == "abort" else "pass"),
                    payload={"status": status},
                    latency_ms=_elapsed_ms(s),
                )
                if status == "abort":
                    return self._deny(req, reason="objective mismatch unresolved", t0=t0)
            else:
                status = "ok"
                self.log.event(qid=qid, stage="cross_correction", decision="pass", payload={"skipped": True})


            # =========================================================
            # 4) 출력 LCE (Output LCE)
            # =========================================================
            if enable_output_lce:
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
                    return self._deny(req, reason="policy/leakage risk by Output LCE", t0=t0)
            else:
                self.log.event(qid=qid, stage="output_lce", decision="allow", payload={"skipped": True})

            # =========================================================
            # 최종 응답 생성 (OK or REPAIRED)
            # =========================================================
            # rolled_back: Tool Verify에 의한 CoT 롤백
            # status == "repaired": Cross-Correction에 의한 텍스트 수정
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
            # 에러를 로그로 남기고 안전 차단 (Fail-Safe)
            self.log.event(
                qid=qid,
                stage="system_exception", 
                decision="deny",
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
