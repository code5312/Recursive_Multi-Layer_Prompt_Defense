#!/usr/bin/env python
# scripts/prepare_data.py
# 사용: python scripts/prepare_data.py --seed 42 [--strict]
from __future__ import annotations
import argparse, json, random
from pathlib import Path
from typing import Dict, Any, List, Tuple
from jsonschema import Draft202012Validator, ValidationError

# 경로 설정
RAW_ATTACKS = Path("data/raw/attacks.jsonl")
RAW_BENIGN  = Path("data/raw/benign.jsonl")
SCHEMA_PATH = Path("data/schemas/sample.schema.json")
OUT_DIR     = Path("data/processed")
INVALID_DIR = Path("results/invalid_samples")

SPLITS = {"train": 0.70, "val": 0.15, "test": 0.15}

# ----- 유틸: 문자열/리스트 정규화 -----
def norm_str(x: Any) -> str:
    return (x or "").strip() if isinstance(x, str) or x is None else str(x).strip()

def norm_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    # 잘못 들어온 값을 리스트로 감싸서라도 손실 없이 유지
    return [x]

# ----- 로딩 -----
def load_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _extract_json_objects(s: str) -> List[str]:
    objs = []
    buf = []
    depth = 0
    in_str = False
    esc = False
    for ch in s:
        buf.append(ch)
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    # 객체 하나 끝
                    obj = ''.join(buf).strip()
                    # 남은 꼬리 텍스트를 다음 추출로 넘기기 위해 buf 초기화
                    objs.append(obj)
                    buf = []
    # 남은 조각에 문자가 있다면(예: 개행/공백 등), 무시
    return objs

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    text = None
    for enc in ("utf-8", "utf-8-sig"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        # 마지막 시도
        text = path.read_text(encoding="utf-8", errors="replace")

    # 개행 정규화 및 흔한 합치기 패턴 1차 완화
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # "}{", "}, {" 같은 패턴은 먼저 개행으로 쪼개본다(대부분의 간단한 케이스 해결)
    import re
    text = re.sub(r'}\s*{', '}\n{', text)
    text = re.sub(r'},\s*{', '}\n{', text)

    out: List[Dict[str, Any]] = []
    bad: List[Tuple[int, str, str]] = []
    for i, raw in enumerate(text.split('\n'), 1):
        line = raw.strip()
        if not line:
            continue

        # 라인에 JSON 객체가 여러 개 붙어 있을 가능성 → 스택기반으로 분리
        candidates = _extract_json_objects(line)
        if not candidates:
            candidates = [line]

        for cand in candidates:
            s = cand.strip()
            if not s:
                continue
            # 혹시 라인이 배열 포맷([{},{}])이면 요소로 분해
            try:
                if s.startswith('[') and s.endswith(']'):
                    arr = json.loads(s)
                    for elem in arr:
                        out.append(elem)
                else:
                    out.append(json.loads(s))
            except Exception as e:
                bad.append((i, s[:200], str(e)))

    if bad:
        INVALID_DIR.mkdir(parents=True, exist_ok=True)
        # 어떤 파일에서 온 건지 표시하기 위해 파일명 포함
        bad_path = INVALID_DIR / f"{path.stem}_parse_bad.jsonl"
        with bad_path.open("w", encoding="utf-8") as fb:
            for i, frag, msg in bad:
                fb.write(json.dumps({"line": i, "error": msg, "frag": frag}, ensure_ascii=False) + "\n")
        print(f"[WARN] {path}: parse errors={len(bad)} → {bad_path}")

    return out

def write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in items:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ----- 전처리/정규화 -----
ALLOWED_ATTACK_TYPES = {"ipi", "target_deviation", "none", "ipi_data_exfiltration", "jailbreak", "data_exfiltration"}

def normalize_record(r: Dict[str, Any]) -> Dict[str, Any]:
    # 공통 필드 존재 보정
    r.setdefault("id", "")
    r.setdefault("input", {})
    r.setdefault("label", {})
    r.setdefault("expected", {})

    # input
    inp = r["input"]
    inp["user_text"] = norm_str(inp.get("user_text"))
    # context_html은 없어도 되지만 있으면 string이어야 함
    if "context_html" in inp:
        inp["context_html"] = norm_str(inp.get("context_html"))
    # tools_allowed는 리스트
    inp["tools_allowed"] = norm_list(inp.get("tools_allowed"))

    # label
    lbl = r["label"]
    lbl["class"] = norm_str(lbl.get("class")) or "benign"
    lbl["attack_type"] = norm_str(lbl.get("attack_type")) or "none"
    # 스키마 enum을 좁게 쓴 경우 대비: 허용셋에 없으면 적절히 매핑
    if lbl["attack_type"] not in ALLOWED_ATTACK_TYPES:
        # 간단 매핑(필요시 커스터마이즈)
        lower = lbl["attack_type"].lower()
        if "ipi" in lower:
            lbl["attack_type"] = "ipi"
        elif "exfil" in lower or "leak" in lower or "data" in lower:
            lbl["attack_type"] = "data_exfiltration"
        elif "jailbreak" in lower:
            lbl["attack_type"] = "jailbreak"
        else:
            lbl["attack_type"] = "target_deviation" if lbl["class"] == "attack" else "none"

    # expected
    exp = r["expected"]
    # should_block가 None이면 라벨에 따라 기본값 설정
    if exp.get("should_block") is None:
        exp["should_block"] = (lbl["class"] == "attack")
    # intent는 없어도 됨 → 존재 시 문자열화
    if "intent" in exp:
        exp["intent"] = norm_str(exp.get("intent"))

    # split 필드는 나중에 채움
    if "split" in r and r["split"] not in ("train", "val", "test"):
        r["split"] = None

    return r

# ----- 검증 (무효 수집 모드) -----
def validate_and_collect(records: List[Dict[str, Any]], schema: Dict[str, Any], name: str, strict: bool) -> List[Dict[str, Any]]:
    validator = Draft202012Validator(schema)
    INVALID_DIR.mkdir(parents=True, exist_ok=True)
    ok, bad = [], []
    for i, rec in enumerate(records):
        rec = normalize_record(rec)
        try:
            validator.validate(rec)
            ok.append(rec)
        except ValidationError as e:
            bad.append({"idx": i, "error": e.message, "record": rec})
    if bad:
        outp = INVALID_DIR / f"{name}_bad.jsonl"
        write_jsonl(outp, bad)
        print(f"[WARN] {name}: {len(bad)} invalid → {outp}")
        if strict:
            # strict 모드에서는 실패로 종료
            raise SystemExit(f"[ERROR] {name} validation failed ({len(bad)}) — see {outp}")
    else:
        print(f"[OK] {name}: all {len(ok)} records valid")
    return ok

# ----- split -----
def stratified_split(items, key_fn, seed: int):
    import random
    random.Random(seed).shuffle(items)

    buckets = {}
    for it in items:
        k = key_fn(it)
        buckets.setdefault(k, []).append(it)

    train, val, test = [], [], []

    for k, arr in buckets.items():
        n = len(arr)
        if n == 1:
            # 샘플 1개인 버킷은 train으로
            train += arr
            continue

        # 기본 배분
        n_train = int(round(n * SPLITS["train"]))
        n_val   = int(round(n * SPLITS["val"]))
        # n_test는 나머지
        n_test  = n - n_train - n_val

        # --- 안전장치: 가능한 한 각 split에 최소 1개 보장 ---
        # 버킷에 샘플이 2개면 train=1, val=1, test=0 식으로 조정
        if n >= 3:
            if n_train == 0: n_train = 1
            if n_val   == 0: n_val   = 1
            if n_test  == 0: n_test  = 1
            # 총합이 초과되면 train에서 빼기
            while n_train + n_val + n_test > n:
                if n_train > 1: n_train -= 1
                elif n_val > 1: n_val -= 1
                elif n_test > 1: n_test -= 1
                else: break
        elif n == 2:
            # 2개면 train=1, val=1, test=0
            n_train, n_val, n_test = 1, 1, 0

        # 슬라이싱
        train += arr[:n_train]
        val   += arr[n_train:n_train+n_val]
        test  += arr[n_train+n_val:n_train+n_val+n_test]

    return train, val, test


def add_split_field(items: List[Dict[str, Any]], split: str) -> None:
    for it in items:
        it["split"] = split

# ----- main -----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--strict", action="store_true", help="유효성 오류 발생 시 즉시 종료")
    args = ap.parse_args()

    schema  = load_schema()
    attacks = read_jsonl(RAW_ATTACKS)
    benign  = read_jsonl(RAW_BENIGN)

    if not attacks and not benign:
        print("[WARN] No raw data found under data/raw/. Nothing to do.")
        return

    # 1) 개별 파일 스키마 검증(무효는 별도로 저장)
    attacks_ok = validate_and_collect(attacks, schema, "attacks", strict=args.strict)
    benign_ok  = validate_and_collect(benign , schema, "benign",  strict=args.strict)

    # 2) 병합
    all_items = attacks_ok + benign_ok

    # 3) stratified split by (class, attack_type)
    def key_fn(r: Dict[str, Any]) -> str:
        cls = r.get("label", {}).get("class", "benign")
        atk = r.get("label", {}).get("attack_type", "none")
        return f"{cls}:{atk}"

    train, val, test = stratified_split(all_items, key_fn, seed=args.seed)

    # 4) split 필드 부여
    add_split_field(train, "train")
    add_split_field(val,   "val")
    add_split_field(test,  "test")

    # 5) 출력
    write_jsonl(OUT_DIR / "train.jsonl", train)
    write_jsonl(OUT_DIR / "val.jsonl",   val)
    write_jsonl(OUT_DIR / "test.jsonl",  test)

    print(f"[OK] Processed → {OUT_DIR}/train|val|test.jsonl")
    print(f" counts: train={len(train)}, val={len(val)}, test={len(test)}")

if __name__ == "__main__":
    main()
