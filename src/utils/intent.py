# src/utils/intent.py
from __future__ import annotations
from typing import Any, Dict

COMMON_PREFIX = ("요약", "정리", "설명", "비교", "추천", "번역", "날씨", "일정", "뉴스", "분석")

class SimpleIntentParser:
    """
    매우 단순한 intent 파서:
    - 첫 단어/동사 기반 goal 추정
    - 특정 키워드가 있으면 명시화
    """
    def parse(self, text: str) -> Dict[str, Any]:
        t = (text or "").strip()
        if not t:
            return {"goal": "unknown"}
        head = t.split()[0]
        for kw in COMMON_PREFIX:
            if kw in t:
                return {"goal": kw}
        return {"goal": head}
