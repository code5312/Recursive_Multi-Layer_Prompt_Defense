from __future__ import annotations
import os, yaml
from typing import Any, Dict

class Config:
    def __init__(self, data: Dict[str, Any]):
        self._data = data or {}

    def get(self, path: str, default: Any = None) -> Any:
        cur: Any = self._data
        for k in path.split("."):
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

def load_config() -> Config:
    path = os.getenv("RECURDEFEND_CONFIG", "configs/default.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config(data)
