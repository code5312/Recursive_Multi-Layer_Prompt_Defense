#!/usr/bin/env python
# scripts/run_baselines.py
#
# E0~E5 방어 조합별 성능 비교
#  - 데이터: data/processed/test.jsonl
#  - metric: precision, recall, f1, bypass_rate

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

from src.app import create_app
from src.orchestrator.orchestrator import OrchestratorRequest

DATA_TEST = Path("data/processed/test.jsonl")
OUT_PATH  = Path("results/baselines.json")

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            out.append(json.loads(line))
    return out

def compute_metrics(golds: List[int], preds: List[int]) -> Dict[str, float]:
    # golds/preds: 1=attack(차단), 0=benign(통과)
    tp = fp = fn = tn = 0
    for g, p in zip(golds, preds):
        if g == 1 and p == 1: tp += 1
        elif g == 0 and p == 1: fp += 1
        elif g == 1 and p == 0: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2*precision*recall / (precision+recall) if (precision+recall) > 0 else 0.0
    bypass    = fn / (tp + fn) if (tp + fn) > 0 else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "bypass_rate": round(bypass, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }

def main():
    app = create_app()
    orc = app.state.orchestrator

    samples = read_jsonl(DATA_TEST)
    print(f"[INFO] test samples = {len(samples)}")

    # gold label: 공격이면 1, 아니면 0
    golds = [1 if s.get("label", {}).get("class") == "attack" else 0 for s in samples]

    settings = {
        # E0: No defense (모든 모듈 비활성)
        "E0_no_defense": dict(
            enable_input_lce=False,
            enable_recursive_cot=False,
            enable_tool_verify=False,
            enable_cross_correction=False,
            enable_output_lce=False,
        ),
        # E1: Input LCE only
        "E1_input_lce_only": dict(
            enable_input_lce=True,
            enable_recursive_cot=False,
            enable_tool_verify=False,
            enable_cross_correction=False,
            enable_output_lce=False,
        ),
        # E2: Output LCE only
        "E2_output_lce_only": dict(
            enable_input_lce=False,
            enable_recursive_cot=False,
            enable_tool_verify=False,
            enable_cross_correction=False,
            enable_output_lce=True,
        ),
        # E3: ToolVerify only (CoT는 활성이나 LCE/CC off)
        "E3_tool_verify_only": dict(
            enable_input_lce=False,
            enable_recursive_cot=True,
            enable_tool_verify=True,
            enable_cross_correction=False,
            enable_output_lce=False,
        ),
        # E4: Cross-Correction only (CoT + CC)
        "E4_cross_correction_only": dict(
            enable_input_lce=False,
            enable_recursive_cot=True,
            enable_tool_verify=False,
            enable_cross_correction=True,
            enable_output_lce=False,
        ),
        # E5: Full defense (현재 기본)
        "E5_full_defense": dict(
            enable_input_lce=True,
            enable_recursive_cot=True,
            enable_tool_verify=True,
            enable_cross_correction=True,
            enable_output_lce=True,
        ),
    }

    results: Dict[str, Any] = {}

    for name, opts in settings.items():
        print(f"[RUN] {name}")
        preds: List[int] = []
        for s in samples:
            rid = s["id"]
            user_text = s["input"].get("user_text") or ""
            ctx_html  = s["input"].get("context_html")
            tools     = s["input"].get("tools_allowed") or []

            req = OrchestratorRequest(
                id=rid,
                user_text=user_text,
                context_html=ctx_html,
                tools_allowed=tools,
                opts=opts,  # 여기서 flags override
            )
            resp = orc.process(req)

            # prediction: status == "blocked" 이면 공격으로 판단(1)
            pred_attack = 1 if resp.status == "blocked" else 0
            preds.append(pred_attack)

        metrics = compute_metrics(golds, preds)
        results[name] = metrics
        print(f"  -> {metrics}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Saved baselines -> {OUT_PATH}")

if __name__ == "__main__":
    main()
