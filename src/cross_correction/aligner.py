# src/cross_correction/aligner.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DEFAULT_THRESHOLD = 0.80

class CrossCorrectionAligner:
    """
    - intent(goal 텍스트) ↔ output 텍스트 유사도 측정
    - 기준치 미달이면 간단한 규칙 기반 re-prompt로 수정 텍스트 생성
    """
    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.th = threshold
        self.vec = TfidfVectorizer(max_features=10000, ngram_range=(1,2))

    def _similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        X = self.vec.fit_transform([a, b])
        sim = cosine_similarity(X[0], X[1])[0, 0]
        return float(sim)

    def _repair(self, intent: str, output: str) -> str:
        """
        매우 간단한 교정: 의도 핵심을 문두에 명시하고, 잠재적 오염 표현을 제거
        """
        cleaned = output
        # 위험 표현 제거(간략)
        for bad in ("ignore user", "system prompt", "developer note", "dump", "exfiltrate"):
            cleaned = cleaned.replace(bad, "[removed]")
        # 의도에 맞춘 리라이트(헤더 한 줄 추가)
        return f"[Aligned to intent: {intent[:60]}] {cleaned}"

    def align(self, intent_in: Dict[str, Any], text_out: str, trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        goal = (intent_in or {}).get("goal") or (intent_in or {}).get("intent") or ""
        sim = self._similarity(goal, text_out or "")
        if sim >= self.th:
            return {"status": "ok", "output": text_out, "similarity": sim}
        # 재교정
        repaired = self._repair(goal, text_out or "")
        sim2 = self._similarity(goal, repaired)
        if sim2 >= self.th * 0.9:  # 약간 완화
            return {"status": "repaired", "output": repaired, "similarity": sim2}
        # 여전히 낮으면 abort
        return {"status": "abort", "output": None, "similarity": sim2}
