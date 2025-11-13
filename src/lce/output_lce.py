# src/lce/output_lce.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

import joblib
import re


class OutputLCE:
    """
    출력 LCE:
      - 응답 텍스트에서 민감 정보/정책 위반 표현을 탐지
      - 규칙 기반 + ML 확률 조합
    """

    def __init__(
        self,
        model_path: str = "models/output_lce",
        threshold: float = 0.65,
    ) -> None:
        self.model_path = Path(model_path)
        self.threshold = float(threshold)

        model_file = self.model_path / "model.joblib"
        if not model_file.exists():
            raise RuntimeError(f"[OutputLCE] model not found: {model_file}")
        self.model = joblib.load(model_file)

        self.risky_keywords = [
            "api_key", "access token", "secret key", "password", "passphrase",
            "주민등록번호", "계좌번호", "카드번호", "신용카드",
            "dump all environment variables", "printenv", "환경변수 전체",
            "private key", "ssh-rsa", "-----BEGIN PRIVATE KEY-----",
        ]

        self.risky_regex = re.compile(
            r"(\d{3}-\d{2}-\d{4}|\d{6}-\d{7})"  # US SSN / 한국 주민등록번호 패턴 등
        )

    def _rule_based_scan(self, text: str) -> Dict[str, Any]:
        low = text.lower()

        for kw in self.risky_keywords:
            if kw.lower() in low:
                return {
                    "score": 0.99,
                    "label": "risk",
                    "signals": {"keyword": kw},
                    "source": "rule",
                }

        m = self.risky_regex.search(text)
        if m:
            return {
                "score": 0.98,
                "label": "risk",
                "signals": {"regex": m.group(0)},
                "source": "regex",
            }

        return {"score": 0.0, "label": "safe", "signals": {}, "source": "none"}

    def predict(self, text: str) -> Dict[str, Any]:
        # 1) 규칙 먼저
        rule_res = self._rule_based_scan(text or "")
        if rule_res["label"] == "risk":
            return rule_res

        # 2) ML 모델
        prob = self.model.predict_proba([text])[0][1]
        label = "risk" if prob >= self.threshold else "safe"

        return {
            "score": float(prob),
            "label": label,
            "signals": {"ml_prob": float(prob)},
            "source": "ml",
        }
