# src/lce/input_lce.py
from __future__ import annotations
import os, re, json
from typing import Any, Dict, Optional
from pathlib import Path

try:
    import joblib
except ImportError:
    joblib = None

HIDDEN_CSS = re.compile(r"display\s*:\s*none", re.I)
ZERO_WIDTH = re.compile(r"\u200B|\u200C|\u200D|\u2060")
META_PROMPT = re.compile(r"(ignore\s+user|system\s+prompt|developer\s+note)", re.I)
ENCODED = re.compile(r"base64|eval\(|decode", re.I)

class InputLCE:
    """
    ML 모델이 있으면 사용(joblib), 없으면 룰 기반으로 score/label 산출.
    모델은 텍스트( user_text + context_html )를 입력으로 받는 TF-IDF + 선형모델을 가정.
    """
    def __init__(self, model_path: str = "models/input_lce", threshold: float = 0.6):
        self.model_path = Path(model_path)
        self.threshold = threshold
        self.model = None
        if joblib and (self.model_path / "model.joblib").exists():
            try:
                self.model = joblib.load(self.model_path / "model.joblib")
            except Exception:
                self.model = None

    def _rules(self, text: str, html: Optional[str]) -> Dict[str, Any]:
        txt = (text or "") + " " + (html or "")
        s_hidden = 1 if HIDDEN_CSS.search(txt) else 0
        s_zero   = 1 if ZERO_WIDTH.search(txt) else 0
        s_meta   = 1 if META_PROMPT.search(txt) else 0
        s_enc    = 1 if ENCODED.search(txt) else 0
        score = min(1.0, 0.25 * (s_hidden + s_zero + s_meta + s_enc))
        label = "risk" if score >= self.threshold else "safe"
        return {"score": float(score), "label": label,
                "signals": {"hidden_css": s_hidden, "zero_width": s_zero, "meta_prompt": s_meta, "encoded_payload": s_enc}}

    def predict(self, x: Dict[str, Any]) -> Dict[str, Any]:
        text = x.get("text") or ""
        html = x.get("html") or ""
        if self.model:
            # 모델은 단일 문자열 입력을 가정
            s = text + "\n" + html
            prob = self.model.predict_proba([s])[0][1] if hasattr(self.model, "predict_proba") else float(self.model.decision_function([s])[0])
            # decision_function은 스케일 다를 수 있어 sigmoid 대체 가능. 여기선 간단히 0..1 clip
            score = max(0.0, min(1.0, float(prob)))
            label = "risk" if score >= self.threshold else "safe"
            return {"score": score, "label": label, "signals": {}}
        return self._rules(text, html)
