# src/lce/train_lce.py
# 사용:
#  - 입력 LCE 학습:  python src/lce/train_lce.py --target input
#  - 출력 LCE 학습:  python src/lce/train_lce.py --target output
# 출력 LCE 학습 데이터 부족 시 공격 샘플을 위험으로 간주하는 프록시 라벨로 시작하므로, 추후 출력 라벨 데이터 추가 시 교체 필요
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report

PROC_DIR = Path("data/processed")
OUT_DIR_INPUT  = Path("models/input_lce")
OUT_DIR_OUTPUT = Path("models/output_lce")

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    arr = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            arr.append(json.loads(line))
    return arr

def load_dataset() -> Tuple[List[Dict], List[Dict]]:
    train = read_jsonl(PROC_DIR / "train.jsonl")
    val   = read_jsonl(PROC_DIR / "val.jsonl")
    return train, val

def build_text_for_input(sample: Dict[str, Any]) -> str:
    s = sample["input"].get("user_text") or ""
    h = sample["input"].get("context_html") or ""
    return s + "\n" + h

def build_text_for_output(sample: Dict[str, Any]) -> str:
    # 출력 LCE는 학습 시 "공격적 출력" 레이블링 데이터가 없으므로
    # proxy로 입력 텍스트 중 유출/정책위반을 유도하는 문구를 긍정클래스로 간주 (초기 베이스라인)
    # 필요 시 별도 아웃풋 라벨 데이터 추가
    return build_text_for_input(sample)

def y_from_input(sample: Dict[str, Any]) -> int:
    # 1 = 위험, 0 = 안전
    return 1 if sample["label"]["class"] == "attack" else 0

def y_from_output(sample: Dict[str, Any]) -> int:
    # 단순 동일 기준(초기): 공격 샘플이면 위험. 향후 출력 라벨 데이터로 교체 권장.
    return 1 if sample["label"]["class"] == "attack" else 0

def train_pipeline(X_train: List[str], y_train: List[int]) -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(max_features=50000, ngram_range=(1,2))),
        ("clf", LogisticRegression(max_iter=200, n_jobs=1))
    ])

def fit_and_eval(target: str) -> None:
    train, val = load_dataset()
    if target == "input":
        X_tr = [build_text_for_input(s) for s in train]
        y_tr = [y_from_input(s) for s in train]
        X_v  = [build_text_for_input(s) for s in val]
        y_v  = [y_from_input(s) for s in val]
        out_dir = OUT_DIR_INPUT
    else:
        X_tr = [build_text_for_output(s) for s in train]
        y_tr = [y_from_output(s) for s in train]
        X_v  = [build_text_for_output(s) for s in val]
        y_v  = [y_from_output(s) for s in val]
        out_dir = OUT_DIR_OUTPUT

    model = train_pipeline(X_tr, y_tr)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_v)
    print("[REPORT]", target)
    print(classification_report(y_v, pred, digits=4))

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / "model.joblib")
    print(f"[OK] Saved → {out_dir/'model.joblib'}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["input","output"], required=True)
    args = ap.parse_args()
    fit_and_eval(args.target)

if __name__ == "__main__":
    main()
