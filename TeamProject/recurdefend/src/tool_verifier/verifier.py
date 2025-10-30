import re
from pydantic import BaseModel, Field
from typing import Dict, Any

class ToolCall(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z_]\w*$")
    args: Dict[str, Any] = {}

ALLOWED_FUNCTIONS = {
    "fetch_data": {"required": ["url"], "optional": ["timeout"]},
    "get_user_info": {"required": ["user_id"], "optional": []},
    "list_files": {"required": [], "optional": ["path"]}
}

def verify_tool_call(call: ToolCall) -> dict:
    if call.name not in ALLOWED_FUNCTIONS:
        return {"verdict": "block", "reason": "disallowed_function"}
    spec = ALLOWED_FUNCTIONS[call.name]
    if not all(k in call.args for k in spec["required"]):
        return {"verdict": "block", "reason": "missing_required_params"}
    # TODO: add type/value checks here
    return {"verdict": "allow"}
