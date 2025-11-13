#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
export UVICORN_RELOAD=${UVICORN_RELOAD:-1}
export RECURDEFEND_TOOLSPECS=${RECURDEFEND_TOOLSPECS:-data/raw/toolspecs.json}

# 기본 포트
PORT=${PORT:-8000}

# 가상환경 감지(Optional)
if [ -d ".venv" ]; then
  # 프로젝트 루트에 `.venv` (Poetry/uv 등) 가 있을 때
  # shellcheck disable=SC1091
  source .venv/bin/activate || true
elif [ -d "venv" ]; then
  # requirements.txt 기반 수동 venv 호환
  # shellcheck disable=SC1091
  source venv/bin/activate || true
fi

# 데이터/로그 폴더 보장
mkdir -p data/processed logs/runtime results/logs logs/training

# 서버 실행
exec uvicorn src.app:app --host 0.0.0.0 --port "${PORT}" ${UVICORN_RELOAD:+--reload}
