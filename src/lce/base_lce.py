# src/lce/base_lce.py
from typing import Dict, Any, Protocol

class BaseLCE(Protocol):
    def predict(self, x: Dict[str, Any]) -> Dict[str, Any]:
        ...