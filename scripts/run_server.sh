#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
export UVICORN_RELOAD=${UVICORN_RELOAD:-1}
export RECURDEFEND_TOOLSPECS=${RECURDEFEND_TOOLSPECS:-data/raw/toolspecs.json}

# 기본 포트
PORT=${PORT:-8000}

# 가상환경 감지(Optional)
if [ -d ".venv" ]; then
  source .venv/bin/activate || true
fi

# 데이터/로그 폴더 보장
mkdir -p data/processed logs/runtime

# 서버 실행
exec uvicorn src.app:app --host 0.0.0.0 --port "${PORT}" ${UVICORN_RELOAD:+--reload}
