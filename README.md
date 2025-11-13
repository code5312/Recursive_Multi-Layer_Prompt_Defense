RecurDefend – Defensive Orchestration for LLaMA Agents
=====================================================

RecurDefend는 LLaMA 계열 에이전트를 대상으로 **입력 필터링 → Recursive Chain-of-Thought → Tool 검증 → Cross-Correction → 출력 필터링** 순의 방어 파이프라인을 제공하는 프로젝트입니다. FastAPI 기반의 서비스와 평가/대시보드 도구를 함께 제공하여 연구와 데모 운영을 동시에 지원합니다.

주요 기능
--------
- **Orchestrator 파이프라인**: 단계별 방어 모듈(Input/Output LCE, Tool Verifier, Cross-Correction)을 직렬로 연결하여 안전한 응답만 반환.
- **Recursive CoT 컨트롤러**: LLM 계획·도구 호출·최종 응답 생성을 안전하게 조율하고 실패 시 롤백 처리.
- **Tool Registry & Verifier**: JSON Schema 기반 툴 스펙 검증, 권한/레이트리밋 정책 적용.
- **Cross-Correction Aligner**: 의도와 출력 간 유사도 검증 및 간단한 자동 교정.
- **데이터/실험 파이프라인**: JSONL 데이터셋, LCE 학습 노트북, 배치 평가 스크립트, Streamlit 대시보드 포함.

폴더 구조 하이라이트
-------------------
- `src/` – FastAPI 앱, 오케스트레이터, 각 방어 모듈 구현.
- `scripts/` – 데이터 증강·머지·평가 스크립트.
- `data/` – raw/processed 데이터와 스키마, 도구 스펙.
- `models/` – LCE 모델(Joblib) 저장 위치.
- `configs/` – 기본 설정 및 실험 구성 YAML.
- `contracts/` – API, 데이터셋, 모듈 I/O 계약 문서.
- `dashboards/` – Streamlit 기반 결과 시각화.
- `tests/` – e2e/integration/unit 테스트 폴더(초기 템플릿).
- `docker/` – 배포용 Dockerfile 및 docker-compose 템플릿.

필수 환경
--------
- Python 3.11 이상
- (선택) GPU + PyTorch 2.2 이상 – 로컬 HF 모델 사용 시
- pip / virtualenv 또는 Conda

로컬 개발 세팅
-------------
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# 환경 변수(LlM 클라이언트)에 따라 OPENAI_COMPAT_API_KEY 등 설정 가능
cp configs/default.yaml configs/local.yaml  # 필요 시 수정
```

FastAPI 실행
-----------
```bash
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

핵심 엔드포인트
--------------
- `POST /v1/agent/query` – 방어 파이프라인 실행
- `GET /v1/logs/{qid}` – 구조화 로그 조회
- `POST /v1/evaluate/run` / `GET /v1/evaluate/results/{job_id}` – 배치 평가
- `GET /v1/tools` – 등록된 툴 목록
- `GET /healthz`, `GET /version`

배치 평가 & 대시보드
------------------
```bash
python src/evaluation/evaluate.py --dataset data/processed/test.jsonl --limit 200
streamlit run dashboards/metrics_app.py
```

테스트
-----
```bash
pytest
```
`tests/unit`에 제공된 예시를 시작점으로 필요한 시나리오별 테스트를 확장하세요.

Docker / 배포 개요
-----------------
- `docker/Dockerfile`을 사용해 서비스 이미지 빌드.
- `docker/docker-compose.yml`은 앱 서버 + (옵션) 대시보드/워크커 컨테이너 구성을 포함.
```bash
docker compose --file docker/docker-compose.yml up --build
```
실제 배포 환경에서는 `.env` 파일에 API 키와 LCE 모델 경로를 지정하고 `configs/default.yaml`을 덮어쓰는 설정 파일을 마운트하십시오.

기타 참고
--------
- `contracts/` 문서를 통해 API 및 데이터 계약을 확인할 수 있습니다.
- `external/InjecAgent`는 벤치마크 데이터와 예제 스크립트를 제공합니다.
- `logs/runtime`에는 구조화된 JSONL 실행 로그가 저장되므로 보존 정책을 고려하세요.

