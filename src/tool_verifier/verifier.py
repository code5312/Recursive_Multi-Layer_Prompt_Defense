# src/tool_verifier/verifier.py
from __future__ import annotations
from typing import Any, Dict, Optional

from src.tool_verifier.registry import ToolRegistry

class RegistryToolVerifier:
    """
    ToolRegistry 기반 툴 호출 검증기.
    orchestrator에서 전달하는 call/user_ctx를 표준화해 registry.check_call로 위임한다.
    """
    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.reg = registry or ToolRegistry()

    def check(self, call: Dict[str, Any], user_ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Args:
          call: {"name": str, "args": dict, ...} 형태를 가정
          user_ctx: {"allowed": [..], "role": "user", "caller": "agent_orchestrator", "user_id": str} 등

        Returns:
          {"allow": bool, "reason": str, "patched_args": Optional[dict], "redact_in_logs": [..]}
        """
        name = (call or {}).get("name")
        args = (call or {}).get("args") or {}

        # 기본 컨텍스트 보강
        role   = (user_ctx or {}).get("role", "user")
        caller = (user_ctx or {}).get("caller", "agent_orchestrator")
        user_id = (user_ctx or {}).get("user_id", "anon")
        allowed_list = (user_ctx or {}).get("allowed") or []

        # 1) 허용 툴 화이트리스트 우선 확인
        if allowed_list and name not in allowed_list:
            return {"allow": False, "reason": "tool_not_allowed", "patched_args": None, "redact_in_logs": []}

        # 2) 레지스트리 정책/스키마 검증
        result = self.reg.check_call(name=name, args=args, user_ctx={
            "role": role,
            "caller": caller,
            "user_id": user_id,
        })

        # 3) 결과 포맷 표준화 (orchestrator가 사용하는 키 유지)
        return {
            "allow": bool(result.get("allow")),
            "reason": result.get("reason", "ok"),
            "patched_args": result.get("patched_args"),
            "redact_in_logs": result.get("redact_in_logs", []),
        }
