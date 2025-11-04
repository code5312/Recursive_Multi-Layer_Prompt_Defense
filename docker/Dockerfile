# docker/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 시스템 의존성(필요 최소)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 프로젝트 복사
COPY . /app

# 포트
EXPOSE 8000

# 데이터/로그 디렉토리
RUN mkdir -p /app/data/processed /app/logs/runtime

ENV RECURDEFEND_TOOLSPECS=/app/data/raw/toolspecs.json

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
