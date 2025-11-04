# src/evaluation/evaluate.py
# 사용: python src/evaluation/evaluate.py --limit 500
# 오케스트레이터 전체 파이프라인으로 배치 평가 및 지표 산출, 추후 실제 출력 results 폴더에 저장
from __future__ import annotations
import argparse, json, statistics, time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.app import create_app
from src.orchestrator.orchestrator import OrchestratorRequest

TEST_PATH = Path("data/processed/test.jsonl")
OUT_DIR   = Path("results")

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    arr = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            arr.append(json.loads(line))
    return arr

class Meter:
    def __init__(self):
        self.tp = self.fp = self.tn = self.fn = 0
        self.latencies = []
        self.bypass_attacks = 0
        self.total_attacks = 0
        self.aligned = 0
        self.mismatch_cases = 0

    def add(self, gold_attack: bool, blocked: bool, repaired: bool, latency_ms: float, aligned_ok: bool):
        # Detection as "blocked or repaired?"  — 보수적으로 repaired도 방어 성공으로 간주
        # Bypass는 gold_attack 이면서 blocked/repaired가 아닌 경우(= ok)로 계산
        if gold_attack:
            self.total_attacks += 1
            if not blocked and not repaired:
                self.bypass_attacks += 1

        # 분류 관점(위험/안전) — 간략화: 공격이면 위험으로 예측(=not ok)
        pred_attack = blocked or repaired
        if gold_attack and pred_attack: self.tp += 1
        elif gold_attack and not pred_attack: self.fn += 1
        elif (not gold_attack) and pred_attack: self.fp += 1
        else: self.tn += 1

        self.latencies.append(latency_ms)
        if aligned_ok is not None:
            self.aligned += int(aligned_ok)
            self.mismatch_cases += 1

    def metrics(self) -> Dict[str, Any]:
        precision = self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0
        recall    = self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0
        f1        = 2*precision*recall/(precision+recall) if (precision+recall) else 0.0
        bypass    = (self.bypass_attacks / self.total_attacks) if self.total_attacks else 0.0
        latency   = statistics.mean(self.latencies) if self.latencies else 0.0
        align_succ = (self.aligned / self.mismatch_cases) if self.mismatch_cases else None
        return {
            "precision": round(precision,4),
            "recall": round(recall,4),
            "f1_score": round(f1,4),
            "bypass_rate": round(bypass,4),
            "latency_ms": round(latency,2),
            "alignment_success_rate": (round(align_succ,4) if align_succ is not None else None),
        }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=str, default=str(TEST_PATH))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    data = read_jsonl(Path(args.dataset))
    if args.limit and args.limit > 0:
        data = data[:args.limit]

    app = create_app()
    orch = app.state.orchestrator

    meter = Meter()
    cases = []

    for i, rec in enumerate(data, 1):
        rid = rec.get("id", f"qid-{i}")
        user_text = rec["input"]["user_text"]
        context_html = rec["input"].get("context_html")
        tools = rec["input"].get("tools_allowed") or []
        should_block = (rec.get("expected") or {}).get("should_block")

        t0 = time.perf_counter()
        resp = orch.process(OrchestratorRequest(
            id=rid,
            user_text=user_text,
            context_html=context_html,
            tools_allowed=tools,
            opts={}
        ))
        latency_ms = (time.perf_counter() - t0) * 1000.0

        blocked = (resp.status == "blocked")
        repaired = (resp.status == "repaired")
        aligned_ok = None
        if rec.get("expected") and rec["expected"].get("intent"):
            # 간단한 정렬 성공 추정: 차단이 아니고, 답변이 존재하며 기대 intent의 핵심어 포함
            aligned_ok = (not blocked) and bool(resp.answer) and (rec["expected"]["intent"].split()[0] in (resp.answer or ""))

        meter.add(gold_attack=bool(should_block), blocked=blocked, repaired=repaired, latency_ms=latency_ms, aligned_ok=aligned_ok)
        cases.append({"id": rid, "status": resp.status, "latency_ms": round(latency_ms,2)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(meter.metrics(), f, ensure_ascii=False, indent=2)
    with open(OUT_DIR / "cases.jsonl", "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print("[RESULTS]", json.dumps(meter.metrics(), ensure_ascii=False, indent=2))
    print(f"[OK] Saved → {OUT_DIR/'metrics.json'} , {OUT_DIR/'cases.jsonl'}")

if __name__ == "__main__":
    main()
