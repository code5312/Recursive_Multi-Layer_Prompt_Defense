import re, time
from .base_lce import BaseLCE

OUT_PATTERNS = [
    (re.compile(r"(admin\s*password|secret\s*token)", re.I), "secret_leak"),
    (re.compile(r"steps\s+to\s+bypass", re.I), "bypass_instruction"),
]

class RuleOutputLCE(BaseLCE):
    def __init__(self, name="rule_output"):
        super().__init__(name)

    def predict(self, text, context=None):
        t0 = time.time()
        evidence, score = [], 0.0
        for pat, desc in OUT_PATTERNS:
            if pat.search(text or ""):
                evidence.append({"type": "pattern", "desc": desc})
                score = max(score, 0.8)
        verdict = "block" if score >= 0.8 else ("flag" if score > 0.3 else "allow")
        res = {"verdict": verdict, "score": score, "labels": [e["desc"] for e in evidence], "evidence": evidence}
        return self._with_latency(res, t0)
