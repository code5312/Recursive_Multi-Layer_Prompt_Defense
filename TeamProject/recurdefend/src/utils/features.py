import re
from typing import Dict

KEYWORDS = [
    r"ignore all previous", r"override", r"bypass", r"admin password",
    r"secret", r"token", r"apikey", r"api_key"
]
KEY_PATTERNS = [re.compile(pat, re.I) for pat in KEYWORDS]

def text_features(s: str) -> Dict[str, float]:
    s = s or ""
    feats = {}
    feats["len_chars"] = float(len(s))
    feats["ratio_upper"] = sum(1 for c in s if c.isupper()) / max(len(s), 1)
    feats["ratio_non_ascii"] = sum(1 for c in s if ord(c) > 127) / max(len(s), 1)
    feats["keyword_hits"] = sum(1 for pat in KEY_PATTERNS if pat.search(s))
    return feats
