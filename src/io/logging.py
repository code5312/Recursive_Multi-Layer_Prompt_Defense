# src/io/logging.py
from __future__ import annotations
import json, os, threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("data/schemas/eventlog.schema.json")

def utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()

def _load_schema() -> Draft202012Validator:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))

def _mask_payload(payload: Dict[str, Any], secrets: List[str]) -> Dict[str, Any]:
    if not payload:
        return {}
    masked = dict(payload)
    # 간단 마스킹: 지정된 키 레벨에서만 **** 처리
    for key in list(masked.keys()):
        if key in secrets and masked[key] is not None:
            masked[key] = "***"
        # 툴 호출 인자(payload.patched_args/args 등) 내부 키 마스킹
        if isinstance(masked[key], dict):
            for k2 in list(masked[key].keys()):
                if k2 in secrets and masked[key][k2] is not None:
                    masked[key][k2] = "***"
    return masked

class StructuredLogger:
    """
    - in-memory store (app.state.log_store) 에 이벤트를 축적
    - 옵션으로 JSONL 파일 기록(logs/runtime/<qid>.jsonl)
    - eventlog.schema.json 으로 각 event를 validate
    """
    def __init__(self, store: Dict[str, List[Dict[str, Any]]], log_dir: str = "logs/runtime", redact_keys: Optional[List[str]] = None, rotate_mb: int = 10):
        self.store = store
        self.log_dir = Path(log_dir)
        self.redact_keys = redact_keys or []
        self.validator = _load_schema()
        self._lock = threading.Lock()
        self.rotate_mb = rotate_mb
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start(self, qid: str) -> None:
        with self._lock:
            self.store[qid] = []

    def end(self, qid: str) -> None:
        # 필요 시 종료 이벤트 추가 가능
        pass

    def _append_to_file(self, qid: str, event: Dict[str, Any]) -> None:
        path = self.log_dir / f"{qid}.jsonl"
        # 간단 로테이션
        if path.exists() and path.stat().st_size > (self.rotate_mb * 1024 * 1024):
            rotated = self.log_dir / f"{qid}.{int(datetime.now().timestamp())}.jsonl"
            path.rename(rotated)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def event(
        self,
        qid: str,
        stage: str,
        decision: Optional[str] = None,
        score: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
        latency_ms: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        evt = {
            "qid": qid,
            "timestamp": utcnow_iso(),
            "stage": stage,
            "decision": decision,
            "score": score,
            "latency_ms": latency_ms,
            "payload": _mask_payload(payload or {}, self.redact_keys),
            # 선택 필드
            "anonymized": True,
        }
        # 스키마 옵션 필드 반영
        for k in ("trace_id", "step_index", "tool_name", "model_info", "policy_flags", "error"):
            if k in kwargs and kwargs[k] is not None:
                evt[k] = kwargs[k]

        # 검증
        for err in self.validator.iter_errors(evt):
            # 개발단계: 실패 시 최소한 스택을 막지 않고 'error' 필드로 기록
            evt.setdefault("error", {"code": "E-SCHEMA", "message": err.message})

        # 저장
        with self._lock:
            self.store.setdefault(qid, []).append(evt)
        # 파일 기록
        self._append_to_file(qid, evt)
