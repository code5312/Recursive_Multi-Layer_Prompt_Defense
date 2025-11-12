#!/usr/bin/env bash
set -euo pipefail

EXPS=(
  "configs/experiments/ablation/full.yaml"
  "configs/experiments/ablation/no_input_lce.yaml"
  "configs/experiments/ablation/no_cross.yaml"
)

mkdir -p results/ablation

for cfg in "${EXPS[@]}"; do
  name=$(basename "$cfg" .yaml)
  echo "[RUN] $name"
  RECURDEFEND_CONFIG="$cfg" python src/evaluation/evaluate.py --limit 0 > "results/ablation/${name}.log" 2>&1 || true
  cp results/metrics.json "results/ablation/metrics_${name}.json" || true
done

echo "[OK] results/ablation/ 아래에 결과 저장됨"
