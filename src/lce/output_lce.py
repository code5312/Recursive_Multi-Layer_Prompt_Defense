# src/lce/output_lce.py
from __future__ import annotations
import re
from typing import Any, Dict, Optional
from pathlib import Path

try:
    import joblib
except ImportError:
    joblib = None

SECRET = re.compile(r"(password|api[_-]?key|token|system\s+prompt)", re.I)
POLICY = re.compile(r"(ignore\s+user|dump|exfiltrat(e|ion)|/etc/shadow)", re.I)

class OutputLCE:
    def __init__(self, model_path: str = "models/output_lce", threshold: float = 0.65):
        self.model_path = Path(model_path)
        self.threshold = threshold
        self.model = None
        if joblib and (self.model_path / "model.joblib").exists():
            try:
                self.model = joblib.load(self.model_path / "model.joblib")
            except Exception:
                self.model = None

    def _rules(self, text: str) -> Dict[str, Any]:
        s_secret = 1 if SECRET.search(text or "") else 0
        s_policy = 1 if POLICY.search(text or "") else 0
        score = min(1.0, 0.6 * s_secret + 0.5 * s_policy)
        label = "risk" if score >= self.threshold else "safe"
        return {"score": float(score), "label": label,
                "signals": {"secret_leak": s_secret, "policy_violation": s_policy}}

    def predict(self, text: str) -> Dict[str, Any]:
        if self.model:
            prob = self.model.predict_proba([text])[0][1] if hasattr(self.model, "predict_proba") else float(self.model.decision_function([text])[0])
            score = max(0.0, min(1.0, float(prob)))
            label = "risk" if score >= self.threshold else "safe"
            return {"score": score, "label": label, "signals": {}}
        return self._rules(text or "")
