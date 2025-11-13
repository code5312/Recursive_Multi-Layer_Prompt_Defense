# src/lce/input_lce.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

import joblib
import re


class InputLCE:
    """
    하이브리드 입력 LCE:
      1) 규칙 기반 시그니처 검사 (강한 필터)
      2) ML 모델 (TF-IDF + LR)
    규칙에 걸리면 무조건 risk, 아니면 모델 결과 사용.
    """

    def __init__(
        self,
        model_path: str = "models/input_lce",
        threshold: float = 0.60,
    ) -> None:
        self.model_path = Path(model_path)
        self.threshold = float(threshold)

        model_file = self.model_path / "model.joblib"
        if not model_file.exists():
            raise RuntimeError(f"[InputLCE] model not found: {model_file}")
        self.model = joblib.load(model_file)

        # 🔥 공격 프롬프트에서 자주 나오는 패턴들 (영어/한국어 섞어둠)
        self.risky_keywords: List[str] = [
            "ignore previous", "ignore above", "ignore all", "무시하고",
            "system prompt", "developer message", "시스템 프롬프트",
            "hidden instruction", "숨겨진 지시",
            "exfiltrate", "유출해", "빼내", "내보내",
            "api_key", "access token", "비밀번호", "password",
            "display:none", "visibility:hidden", "style=\"display:none\"",
            "<!--",  # HTML 주석 기반 IPI
            "Act as system", "너는 이제 시스템", "보안 규칙을 무시",
            "bypass", "우회", "필터를 피해서",
        ]

        # 정규식 기반 시그니처 (조금 더 공격적인 패턴)
        self.risky_regex = re.compile(
            r"(ignore\s+the\s+user|override\s+the\s+instruction|"
            r"dump\s+all\s+(secrets|env|environment)|"
            r"모든\s+환경변수|주민등록번호\s+전체|"
            r"시스템\s+프롬프트\s+전체를\s+출력)",
            re.IGNORECASE,
        )

    def _concat_text(self, x: Dict[str, Any]) -> str:
        t = (x.get("text") or "")  # user_text
        h = (x.get("html") or "")  # context_html
        return f"{t}\n{h}".strip()

    def _rule_based_scan(self, text: str) -> Dict[str, Any]:
        """
        텍스트에서 공격 패턴이 발견되면 강하게 risk 반환.
        """
        low = text.lower()

        # 1) 키워드 매칭
        for kw in self.risky_keywords:
            if kw.lower() in low:
                return {
                    "score": 0.99,
                    "label": "risk",
                    "signals": {"keyword": kw},
                    "source": "rule",
                }

        # 2) 정규식 매칭
        m = self.risky_regex.search(low)
        if m:
            return {
                "score": 0.98,
                "label": "risk",
                "signals": {"regex": m.group(0)},
                "source": "regex",
            }

        # 룰에 안 걸리면 None
        return {"score": 0.0, "label": "safe", "signals": {}, "source": "none"}

    def predict(self, x: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrator에서 호출되는 메인 엔트리.
        x = {"text": user_text, "html": context_html}
        """
        text = self._concat_text(x)

        # 1) 규칙 기반 먼저
        rule_res = self._rule_based_scan(text)
        if rule_res["label"] == "risk":
            return rule_res

        # 2) ML 모델 점수
        prob = self.model.predict_proba([text])[0][1]  # class=1 (attack) 확률
        label = "risk" if prob >= self.threshold else "safe"

        return {
            "score": float(prob),
            "label": label,
            "signals": {"ml_prob": float(prob)},
            "source": "ml",
        }
