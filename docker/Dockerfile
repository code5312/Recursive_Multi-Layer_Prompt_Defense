# docker/Dockerfile
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 시스템 의존성(필요 최소)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 비루트 사용자 생성
RUN groupadd --system app && useradd --system --gid app --shell /bin/bash app

COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

# 프로젝트 복사 (권한 유지)
COPY --chown=app:app . .

# 데이터/로그 디렉토리
RUN mkdir -p /app/data/processed /app/logs/runtime && \
    chown -R app:app /app/data /app/logs

USER app

ENV RECURDEFEND_TOOLSPECS=/app/data/raw/toolspecs.json \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000 \
    UVICORN_WORKERS=2

EXPOSE 8000

CMD ["sh", "-c", "uvicorn src.app:app --host ${UVICORN_HOST:-0.0.0.0} --port ${UVICORN_PORT:-8000} --workers ${UVICORN_WORKERS:-2}"]
