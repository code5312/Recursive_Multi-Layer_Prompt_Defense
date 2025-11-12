# scripts/prepare_data.py
# 사용: python scripts/prepare_data.py --seed 42
from __future__ import annotations
import argparse, json, os, random, sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from jsonschema import Draft202012Validator

RAW_ATTACKS = Path("data/raw/attacks.jsonl")
RAW_BENIGN  = Path("data/raw/benign.jsonl")
SCHEMA_PATH = Path("data/schemas/sample.schema.json")
OUT_DIR     = Path("data/processed")

SPLITS = {"train": 0.70, "val": 0.15, "test": 0.15}

def load_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_records(records: List[Dict[str, Any]], schema: Dict[str, Any], name: str) -> None:
    validator = Draft202012Validator(schema)
    errs = []
    for i, rec in enumerate(records):
        for e in validator.iter_errors(rec):
            errs.append((i, e.message))
    if errs:
        print(f"[ERROR] {name} schema validation failed with {len(errs)} errors:", file=sys.stderr)
        for i, msg in errs[:10]:
            print(f"  - idx={i}: {msg}", file=sys.stderr)
        sys.exit(1)

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            out.append(json.loads(line))
    return out

def write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in items:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def stratified_split(items: List[Dict[str, Any]], key_fn, seed: int) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    # 그룹(라벨)별로 동일 비율 유지
    random.Random(seed).shuffle(items)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        k = key_fn(it)
        buckets.setdefault(k, []).append(it)
    train, val, test = [], [], []
    for k, arr in buckets.items():
        n = len(arr)
        n_train = int(round(n * SPLITS["train"]))
        n_val   = int(round(n * SPLITS["val"]))
        n_test  = n - n_train - n_val
        train += arr[:n_train]
        val   += arr[n_train:n_train+n_val]
        test  += arr[n_train+n_val:]
    return train, val, test

def add_split_field(items: List[Dict[str, Any]], split: str) -> None:
    for it in items:
        it["split"] = split

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    schema = load_schema()
    attacks = read_jsonl(RAW_ATTACKS)
    benign  = read_jsonl(RAW_BENIGN)

    if not attacks and not benign:
        print("[WARN] No raw data found under data/raw/. Nothing to do.")
        return

    # 1) 개별 파일 스키마 검증(라벨 일관성은 계약상 신뢰)
    validate_records(attacks, schema, "attacks.jsonl")
    validate_records(benign , schema, "benign.jsonl")

    # 2) 병합
    all_items = attacks + benign

    # 3) stratified split by (class, attack_type)
    key_fn = lambda r: f'{r["label"]["class"]}:{r["label"]["attack_type"]}'
    train, val, test = stratified_split(all_items, key_fn, seed=args.seed)

    # 4) split 필드 부여
    add_split_field(train, "train"); add_split_field(val, "val"); add_split_field(test, "test")

    # 5) 출력
    write_jsonl(OUT_DIR / "train.jsonl", train)
    write_jsonl(OUT_DIR / "val.jsonl",   val)
    write_jsonl(OUT_DIR / "test.jsonl",  test)

    print(f"[OK] Processed → {OUT_DIR}/train|val|test.jsonl")
    print(f" counts: train={len(train)}, val={len(val)}, test={len(test)}")

if __name__ == "__main__":
    main()
