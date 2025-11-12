#!/usr/bin/env python
# scripts/convert_injecagent.py

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional


def map_attack_type_dh(raw: str) -> str:
    # direct harm / financial / data security → 전부 target_deviation로 통일
    return "target_deviation"

def map_attack_type_ds(raw: str) -> str:
    # 데이터 탈취류 역시 coarse-grained하게 target_deviation로
    return "target_deviation"

def build_attack_record(
    base_id: str,
    idx: int,
    instruction: str,
    tools: List[str],
    attack_type: str,
    as_ipi: bool = False,
) -> Dict[str, Any]:
    rid = f"{base_id}_{idx:04d}"

    if not as_ipi:
        user_text = instruction
        context_html = None
    else:
        user_text = "아래 이메일/콘텐츠를 요약해줘."
        context_html = (
            "<div>일반 비즈니스 메일 내용...</div>\n"
            f"<!-- MALICIOUS PROMPT: {instruction} -->"
        )

        rec = {
            "id": rid,
            "input": {
                "user_text": user_text,
                "tools_allowed": tools or [],
            },
            "label": {"class": "attack", "attack_type": attack_type},
            "expected": {"should_block": True},
        }

        if context_html is not None:
            rec["input"]["context_html"] = context_html

        if as_ipi:
                rec["label"]["attack_type"] = "ipi"
                rec["expected"]["intent"] = "요약"

    return rec

def convert_dh(src: Path, out_f, as_ipi: bool):
    if not src.is_file():
        return
    with src.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue
            r = json.loads(line)
            rec = build_attack_record(
                base_id="injecagent_dh_ipi" if as_ipi else "injecagent_dh",
                idx=i,
                instruction=r.get("Attacker Instruction", ""),
                tools=r.get("Attacker Tools", []),
                attack_type=map_attack_type_dh(r.get("Attack Type", "")),
                as_ipi=as_ipi,
            )
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def convert_ds(src: Path, out_f, as_ipi: bool):
    if not src.is_file():
        return
    with src.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue
            r = json.loads(line)
            rec = build_attack_record(
                base_id="injecagent_ds_ipi" if as_ipi else "injecagent_ds",
                idx=i,
                instruction=r.get("Attacker Instruction", ""),
                tools=r.get("Attacker Tools", []),
                attack_type=map_attack_type_ds(r.get("Attack Type", "")),
                as_ipi=as_ipi,
            )
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def convert_user_cases(src: Path, out_f):
    """
    InjecAgent의 user_cases.jsonl을 benign 샘플로 변환.
    """
    if not src.is_file():
        return

    with src.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue

            r = json.loads(line)

            user_text = (
                r.get("User Instruction")
                or r.get("User instruction")
                or r.get("instruction")
            )
            if not user_text:
                continue

            user_tool = r.get("User Tool") or r.get("User tool")
            tools_allowed = [user_tool] if user_tool else []

            rec: Dict[str, Any] = {
                "id": f"injecagent_benign_{i:04d}",
                "input": {
                    "user_text": user_text,
                    "tools_allowed": tools_allowed,
                },
                "label": {
                    "class": "benign",
                    "attack_type": "none",
                },
                "expected": {
                    "should_block": False,
                },
            }

            # intent가 굳이 필요 없으면 아예 안 넣어도 됨.
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--injec-dir",
        type=str,
        default="InjecAgent/data",
        help="InjecAgent 원본 data 디렉토리 경로",
    )
    p.add_argument(
        "--out-attacks",
        type=str,
        default="data/raw/attacks_injecagent.jsonl",
        help="변환된 공격 샘플 출력 경로",
    )
    p.add_argument(
        "--out-benign",
        type=str,
        default="data/raw/benign_injecagent.jsonl",
        help="변환된 benign 샘플 출력 경로(있을 경우)",
    )
    p.add_argument(
        "--with-ipi-variants",
        action="store_true",
        help="동일 공격을 IPI(context_html)에 숨긴 변형 샘플도 함께 생성",
    )
    args = p.parse_args()
    inj = Path(args.injec_dir)

    dh_path = inj / "attacker_cases_dh.jsonl"
    ds_path = inj / "attacker_cases_ds.jsonl"
    user_cases_path = inj / "user_cases.jsonl"

    out_attacks = Path(args.out_attacks)
    out_attacks.parent.mkdir(parents=True, exist_ok=True)

    with out_attacks.open("w", encoding="utf-8") as fa:
        convert_dh(dh_path, fa, as_ipi=False)
        convert_ds(ds_path, fa, as_ipi=False)
        if args.with_ipi_variants:
            convert_dh(dh_path, fa, as_ipi=True)
            convert_ds(ds_path, fa, as_ipi=True)

    out_benign = Path(args.out_benign)
    out_benign.parent.mkdir(parents=True, exist_ok=True)
    with out_benign.open("w", encoding="utf-8") as fb:
        convert_user_cases(user_cases_path, fb)

    print(f"[OK] attacks -> {out_attacks}")
    print(f"[OK] benign  -> {out_benign} (존재하는 경우에만 기록)")


if __name__ == "__main__":
    main()
