import re, time
from .base_lce import BaseLCE

PATTERNS = [
    (re.compile(r"ignore all previous", re.I), "instruction_override"),
    (re.compile(r"(secret|password|token|apikey|api_key)", re.I), "sensitive_request"),
    (re.compile(r"\bexec\(|\beval\(", re.I), "code_exec"),
    (re.compile(r"bypass\s+firewall", re.I), "bypass")
]

class RuleInputLCE(BaseLCE):
    def __init__(self, name="rule_input"):
        super().__init__(name)

    def predict(self, text, context=None):
        t0 = time.time()
        evidence = []
        score = 0.0
        for pat, desc in PATTERNS:
            if pat.search(text or ""):
                evidence.append({"type": "pattern", "desc": desc})
                score = max(score, 0.8)
        if score >= 0.8:
            verdict = "block"
        elif score > 0.3:
            verdict = "flag"
        else:
            verdict = "allow"
        res = {"verdict": verdict, "score": score, "labels": [e["desc"] for e in evidence], "evidence": evidence}
        return self._with_latency(res, t0)
