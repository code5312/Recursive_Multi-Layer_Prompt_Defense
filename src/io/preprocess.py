# src/io/preprocess.py
from __future__ import annotations
from typing import Optional

def norm_str(x: Optional[str]) -> str:
    return (x or "").strip()

def coalesce(a, b):
    return a if a is not None else b
