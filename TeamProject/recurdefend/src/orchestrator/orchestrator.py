from typing import List, Dict, Any

def aggregate(results: List[Dict[str, Any]], block_threshold=0.9, mean_flag_threshold=0.6) -> str:
    scores = [r.get("score", 0.0) for r in results]
    verdicts = [r.get("verdict", "allow") for r in results]
    # strong block
    if any((v == "block" and s >= block_threshold) for v, s in zip(verdicts, scores)):
        return "block"
    # mean risk -> flag
    mean_score = sum(scores) / max(len(scores), 1)
    if mean_score >= mean_flag_threshold:
        return "flag"
    # majority flag
    if verdicts.count("flag") > len(verdicts) / 2:
        return "flag"
    return "allow"

def should_escalate(results: List[Dict[str, Any]]) -> bool:
    v = [r.get("verdict") for r in results]
    return ("flag" in v) or (("block" in v) and ("allow" in v))
