# src/lce/train_lce.py
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, confusion_matrix
import numpy as np
import collections
import re

PROC_DIR = Path("data/processed")
OUT_DIR_INPUT  = Path("models/input_lce")
OUT_DIR_OUTPUT = Path("models/output_lce")

RES_INPUT  = Path("results/lce_input")
RES_OUTPUT = Path("results/lce_output")

# --- 추가: cleanse 함수 ---
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
SCRIPT_BLOCK = re.compile(r"<script.*?>.*?</script>", re.S|re.I)
STYLE_BLOCK  = re.compile(r"<style.*?>.*?</style>",  re.S|re.I)
HTML_TAGS    = re.compile(r"<[^>]+>")
URL_PATTERN  = re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.I)
EMAIL_PATTERN= re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
DIGITS       = re.compile(r"\d+")
CODEFENCE    = re.compile(r"```.*?```", re.S)  # markdown code block
WHITES       = re.compile(r"\s+")

def cleanse(txt: str) -> str:
    """누수성/편향 토큰 제거 및 정규화"""
    if not txt: 
        return ""
    x = txt
    x = CODEFENCE.sub(" ", x)
    x = HTML_COMMENT.sub(" ", x)
    x = SCRIPT_BLOCK.sub(" ", x)
    x = STYLE_BLOCK.sub(" ", x)
    x = HTML_TAGS.sub(" ", x)
    x = URL_PATTERN.sub(" URL ", x)
    x = EMAIL_PATTERN.sub(" EMAIL ", x)
    x = DIGITS.sub("0", x)
    x = WHITES.sub(" ", x)
    return x.strip()

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
    # 현재는 입력 텍스트를 그대로 사용(출력 라벨 없을 때의 프록시 학습)
    return build_text_for_input(sample)

def y_from_input(sample: Dict[str, Any]) -> int:
    # 1 = 위험(attack), 0 = 안전(benign)
    return 1 if sample["label"]["class"] == "attack" else 0

def y_from_output(sample: Dict[str, Any]) -> int:
    # 초기 프록시: 공격 샘플이면 위험
    return 1 if sample["label"]["class"] == "attack" else 0

# --- 교체: make_pipeline() ---
def make_pipeline() -> Pipeline:
    vec = TfidfVectorizer(
        preprocessor=cleanse,        # <- 핵심: 여기서 정제
        lowercase=True,
        strip_accents="unicode",
        token_pattern=r"(?u)\b[\w@#\$%\-]+\b",  # 특수문자 일부 허용
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.98,                 # 너무 흔한 토큰 제외
        max_features=30000,
        sublinear_tf=True,
    )
    clf = LogisticRegression(
        solver="saga",
        class_weight="balanced",
        C=2.0,
        max_iter=2000,
        n_jobs=-1,
        random_state=42,
    )
    return Pipeline([("tfidf", vec), ("clf", clf)])

def dump_report(target: str, y_true, y_pred, vec_vocab_size: int):
    if target == "input":
        out_dir = RES_INPUT
    else:
        out_dir = RES_OUTPUT
    out_dir.mkdir(parents=True, exist_ok=True)

    # classification report
    report_txt = classification_report(y_true, y_pred, digits=4)
    (out_dir / "report.txt").write_text(report_txt, encoding="utf-8")

    # confusion matrix
    cm = confusion_matrix(y_true, y_pred, labels=[0,1])
    np.save(out_dir / "confusion.npy", cm)

    # 간단 메타 정보
    meta = {
        "vocab_size": vec_vocab_size,
        "support": {
            "y_true": collections.Counter(map(int, y_true)),
            "y_pred": collections.Counter(map(int, y_pred)),
        }
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[REPORT]", target)
    print(report_txt)
    print(f"[OK] Saved report/confusion/meta -> {out_dir}")

def fit_and_eval(target: str) -> None:
    train, val = load_dataset()

    if target == "input":
        X_tr = [build_text_for_input(s) for s in train]
        y_tr = [y_from_input(s) for s in train]
        X_v  = [build_text_for_input(s) for s in val]
        y_v  = [y_from_input(s) for s in val]
        model_out_dir = OUT_DIR_INPUT
        res_dir = RES_INPUT
    else:
        X_tr = [build_text_for_output(s) for s in train]
        y_tr = [y_from_output(s) for s in train]
        X_v  = [build_text_for_output(s) for s in val]
        y_v  = [y_from_output(s) for s in val]
        model_out_dir = OUT_DIR_OUTPUT
        res_dir = RES_OUTPUT

    # 결과 디렉토리 정리(이전 리포트만)
    for p in [res_dir / "report.txt", res_dir / "confusion.npy", res_dir / "meta.json"]:
        if p.exists(): p.unlink()

    model = make_pipeline()
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_v)

    # 벡터라이저 어휘수 로그
    vec = model.named_steps["tfidf"]
    vocab_size = len(vec.vocabulary_) if hasattr(vec, "vocabulary_") and vec.vocabulary_ else 0

    dump_report(target, y_v, y_pred, vec_vocab_size=vocab_size)

    model_out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_out_dir / "model.joblib")
    print(f"[OK] Saved → {model_out_dir/'model.joblib'}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["input","output"], required=True)
    args = ap.parse_args()
    fit_and_eval(args.target)

if __name__ == "__main__":
    main()
