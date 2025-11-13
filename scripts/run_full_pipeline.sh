#!/usr/bin/env bash
set -e

echo "[1] 데이터 전처리"
python scripts/prepare_data.py --seed 42

echo "[2] LCE 재학습 (input/output)"
python -m src.lce.train_lce --target input
python -m src.lce.train_lce --target output

echo "[3] E2E 평가"
python -m src.evaluation.evaluate --limit 0
