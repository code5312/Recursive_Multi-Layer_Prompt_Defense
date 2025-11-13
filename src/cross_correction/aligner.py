# src/cross_correction/aligner.py
from __future__ import annotations
from typing import Any, Dict, List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DEFAULT_THRESHOLD = 0.78   # 살짝 완화 (기존 0.80 → 0.78)

SUSPICIOUS_PATTERNS = [
    "ignore previous instructions",
    "ignore the user",
    "시스템 프롬프트",
    "system prompt",
    "developer note",
    "internal instruction",
    "dump all",
    "exfiltrate",
    "환경 변수 전체를 출력",
    "내부 설정을 모두 보여줘",
]

class CrossCorrectionAligner:
    """
    - intent(goal) ↔ output 텍스트 유사도 측정
    - 기준치 미달 + 수상한 표현 포함 시 규칙 기반 정정
    """
    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.th = threshold
        self.vec = TfidfVectorizer(
            max_features=8000,
            ngram_range=(1, 2),
            min_df=2,
        )

    def _similarity(self, a: str, b: str) -> float:
        a = (a or "").strip()
        b = (b or "").strip()
        if not a or not b:
            return 0.0
        # 아주 짧은 intent는 유사도 신뢰도 낮음 → 그대로 통과 쪽으로
        if len(a) < 5:
            return 1.0
        X = self.vec.fit_transform([a, b])
        sim = cosine_similarity(X[0], X[1])[0, 0]
        return float(sim)

    def _contains_suspicious(self, text: str) -> bool:
        t = (text or "").lower()
        for pat in SUSPICIOUS_PATTERNS:
            if pat.lower() in t:
                return True
        return False

    def _repair(self, intent: str, output: str) -> str:
        """
        - 위험 표현 제거
        - 의도 요약을 문두에 명시
        """
        cleaned = output or ""
        for bad in SUSPICIOUS_PATTERNS:
            cleaned = cleaned.replace(bad, "[removed]")

        header = f"[Aligned to intent: {intent[:60]}] " if intent else "[Aligned output] "
        return header + cleaned

    def align(self, intent_in: Dict[str, Any], text_out: str, trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        goal = (intent_in or {}).get("goal") or (intent_in or {}).get("intent") or ""
        out = text_out or ""

        sim = self._similarity(goal, out)
        suspicious = self._contains_suspicious(out)

        # 1) 충분히 유사하고 수상한 패턴도 없으면 그대로 통과
        if sim >= self.th and not suspicious:
            return {
                "status": "ok",
                "output": out,
                "similarity": sim,
                "suspicious": False,
            }

        # 2) 의도와 유사도는 낮지만, 수상한 표현이 섞여 있으면 정정 시도
        if suspicious:
            repaired = self._repair(goal, out)
            sim2 = self._similarity(goal, repaired)
            if sim2 >= self.th * 0.9:
                return {
                    "status": "repaired",
                    "output": repaired,
                    "similarity": sim2,
                    "suspicious": True,
                }
            else:
                return {
                    "status": "abort",
                    "output": None,
                    "similarity": sim2,
                    "suspicious": True,
                }

        # 3) 수상하진 않지만, 의도와 너무 다르면 abort (안전 차단)
        return {
            "status": "abort",
            "output": None,
            "similarity": sim,
            "suspicious": False,
        }
