# src/tool_verifier/registry.py
from __future__ import annotations
import json, os, threading, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jsonschema import Draft202012Validator

TOOLSPECS_PATH = Path(os.getenv("RECURDEFEND_TOOLSPECS", "data/raw/toolspecs.json"))
SCHEMA_PATH    = Path("data/schemas/tool.schema.json")

def _load_schema() -> Draft202012Validator:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))

def _as_list(x):
    return x if isinstance(x, list) else [x]

class ToolRegistry:
    """툴 스펙 로딩/검증/조회 및 호출 검증(스키마·권한·레이트리밋)."""
    def __init__(self, toolspecs_path: Path = TOOLSPECS_PATH):
        self.toolspecs_path = toolspecs_path
        self.validator = _load_schema()
        self._lock = threading.Lock()
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._rates: Dict[Tuple[str, str], List[float]] = {}  # (tool,user) -> timestamps
        self.reload()

    def reload(self) -> None:
        if not self.toolspecs_path.exists():
            self._tools = {}
            return
        with open(self.toolspecs_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        entries: List[Dict[str, Any]] = content if isinstance(content, list) else [content]
        tools: Dict[str, Dict[str, Any]] = {}
        for ent in entries:
            errs = list(self.validator.iter_errors(ent))
            if errs:
                # 유효하지 않은 스펙은 건너뜀
                continue
            tools[ent["name"]] = ent
        with self._lock:
            self._tools = tools

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self._tools.get(name)

    # --------------- 검증 핵심 ---------------
    def _check_role(self, spec: Dict[str, Any], role: str) -> bool:
        min_role = (((spec.get("policy") or {}).get("min_role")) or "user")
        order = {"guest": 0, "user": 1, "admin": 2}
        return order.get(role or "guest", 0) >= order[min_role]

    def _check_rate(self, spec: Dict[str, Any], tool: str, user: str) -> bool:
        limit = ((spec.get("policy") or {}).get("rate_limit_per_min") or 0)
        if limit <= 0:
            return True
        k = (tool, user or "anon")
        now = time.time()
        with self._lock:
            arr = self._rates.setdefault(k, [])
            # 최근 60초만 유지
            arr = [t for t in arr if now - t < 60]
            if len(arr) >= limit:
                self._rates[k] = arr
                return False
            arr.append(now)
            self._rates[k] = arr
        return True

    def _coerce_type(self, t: str, v: Any) -> bool:
        if v is None:
            return True
        if t == "string":   return isinstance(v, str)
        if t == "integer":  return isinstance(v, int) and not isinstance(v, bool)
        if t == "number":   return isinstance(v, (int, float)) and not isinstance(v, bool)
        if t == "boolean":  return isinstance(v, bool)
        if t == "object":   return isinstance(v, dict)
        if t == "array":    return isinstance(v, list)
        return False

    def _validate_params(self, spec: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        schema_params = (spec.get("params") or {})
        patched = dict(args or {})
        # required & type & enum & bounds
        for pname, pdef in schema_params.items():
            req = pdef.get("required", False)
            if req and pname not in patched:
                return False, None, f"missing_param:{pname}"
            if pname in patched:
                v = patched[pname]
                ptype = pdef.get("type")
                if ptype and not self._coerce_type(ptype, v):
                    return False, None, f"type_mismatch:{pname}"
                if "enum" in pdef and pdef["enum"]:
                    if v not in pdef["enum"]:
                        return False, None, f"enum_mismatch:{pname}"
                if isinstance(v, str):
                    if "minLength" in pdef and len(v) < pdef["minLength"]:
                        return False, None, f"min_length:{pname}"
                    if "maxLength" in pdef and len(v) > pdef["maxLength"]:
                        return False, None, f"max_length:{pname}"
                if isinstance(v, (int, float)):
                    if "minimum" in pdef and v < pdef["minimum"]:
                        return False, None, f"minimum:{pname}"
                    if "maximum" in pdef and v > pdef["maximum"]:
                        return False, None, f"maximum:{pname}"
        # safe_defaults 적용
        safe_defaults = ((spec.get("policy") or {}).get("safe_defaults")) or {}
        for k, v in safe_defaults.items():
            if k in schema_params and (patched.get(k) is None):
                patched[k] = v
        return True, patched, "ok"

    def check_call(self, name: str, args: Dict[str, Any], user_ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        반환: {"allow": bool, "reason": str, "patched_args": Optional[dict], "redact_in_logs": [..]}
        정책:
         - 미등록 툴: allow=false (unknown)
         - 역할 부족: allow=false (role)
         - 레이트리밋 초과: allow=false (rate)
         - 파라미터 미스매치: deny_on_schema_mismatch이면 allow=false, 아니면 patch 시도
        """
        spec = self.get(name)
        if not spec:
            return {"allow": False, "reason": "unknown_tool", "patched_args": None, "redact_in_logs": []}

        role = (user_ctx or {}).get("role", "user")
        caller = (user_ctx or {}).get("caller", "agent_orchestrator")
        allowed_callers = ((spec.get("policy") or {}).get("allowed_callers") or [])

        if allowed_callers and caller not in allowed_callers:
            return {"allow": False, "reason": "caller_not_allowed", "patched_args": None, "redact_in_logs": []}

        if not self._check_role(spec, role):
            return {"allow": False, "reason": "role_insufficient", "patched_args": None, "redact_in_logs": []}

        if not self._check_rate(spec, name, user_ctx.get("user_id", "anon")):
            return {"allow": False, "reason": "rate_limited", "patched_args": None, "redact_in_logs": []}

        ok, patched, reason = self._validate_params(spec, args or {})
        if not ok:
            deny_on_mismatch = ((spec.get("policy") or {}).get("deny_on_schema_mismatch"))
            if deny_on_mismatch:
                return {"allow": False, "reason": f"schema_mismatch:{reason}", "patched_args": None, "redact_in_logs": (spec.get("policy") or {}).get("redact_in_logs", [])}
            # fallback: 패치 불가 → deny
            return {"allow": False, "reason": f"invalid_args:{reason}", "patched_args": None, "redact_in_logs": (spec.get("policy") or {}).get("redact_in_logs", [])}

        return {"allow": True, "reason": "ok", "patched_args": patched, "redact_in_logs": (spec.get("policy") or {}).get("redact_in_logs", [])}
