#!/usr/bin/env python
# scripts/merge_sources.py
# data/raw 내부의 attacks*.jsonl, benign*.jsonl를 모아
#   -> data/raw/attacks.jsonl, data/raw/benign.jsonl 로 재생성
# 규칙:
#  - UTF-8로 읽기
#  - 스키마 최소 필수 키 존재 여부 체크 후만 포함
#  - id 중복 제거(마지막 것으로 덮지 않고 최초 것을 유지)
#  - benign_fixed.jsonl, *_aug_*.jsonl 등 자동 포함

import json, sys, re
from pathlib import Path

RAW = Path("data/raw")
OUT_ATTACKS = RAW / "attacks.jsonl"
OUT_BENIGN  = RAW / "benign.jsonl"

def good_attack(r):
    try:
        return (r.get("label",{}).get("class")=="attack"
                and isinstance(r.get("input",{}).get("user_text",""), str))
    except Exception:
        return False

def good_benign(r):
    try:
        return (r.get("label",{}).get("class")=="benign"
                and isinstance(r.get("input",{}).get("user_text",""), str))
    except Exception:
        return False

def read_jsonl(p: Path):
    try:
        txt = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 윈도우에서 cp949로 저장된 경우 대비
        txt = p.read_text(encoding="cp949", errors="ignore")
    for line in txt.splitlines():
        line=line.strip()
        if not line: continue
        try:
            yield json.loads(line)
        except Exception:
            continue

def main():
    if not RAW.exists():
        print("[ERR] data/raw not found"); sys.exit(1)

    # 병합 대상: attacks*.jsonl / benign*.jsonl (merged output은 제외)
    attack_files = sorted([p for p in RAW.glob("attacks*.jsonl") if p.name not in {"attacks.jsonl"}])
    benign_files = sorted([p for p in RAW.glob("benign*.jsonl")  if p.name not in {"benign.jsonl"}])

    # benign_fixed가 있다면 최우선 포함(앞쪽에 두기)
    benign_files = sorted(benign_files, key=lambda x: (0 if "benign_fixed" in x.name else 1, x.name))

    seen_ids = set()
    attacks_out, benign_out = [], []

    for p in attack_files:
        for r in read_jsonl(p):
            rid = r.get("id") or f"atk_{len(attacks_out)}"
            if rid in seen_ids: continue
            if good_attack(r):
                attacks_out.append(r); seen_ids.add(rid)

    for p in benign_files:
        for r in read_jsonl(p):
            rid = r.get("id") or f"ben_{len(benign_out)}"
            if rid in seen_ids: continue
            if good_benign(r):
                # context_html이 None이면 빈 문자열로 통일(스키마 string 강제 가정)
                if r.get("input",{}).get("context_html") is None:
                    r["input"]["context_html"] = ""
                # attack_type은 항상 "none"으로 강제
                r["label"]["attack_type"] = "none"
                benign_out.append(r); seen_ids.add(rid)

    OUT_ATTACKS.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in attacks_out), encoding="utf-8")
    OUT_BENIGN.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in benign_out),  encoding="utf-8")

    print(f"[OK] merged attacks -> {OUT_ATTACKS} ({len(attacks_out)})")
    print(f"[OK] merged benign  -> {OUT_BENIGN}  ({len(benign_out)})")

if __name__ == "__main__":
    main()
