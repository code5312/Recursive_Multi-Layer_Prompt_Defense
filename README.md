<div align="center">

<img alt="python" src="https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white" />
<img alt="fastapi" src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" />
<img alt="pytorch" src="https://img.shields.io/badge/PyTorch-EE4C2C?style=flat&logo=pytorch&logoColor=white" />
<img alt="topic" src="https://img.shields.io/badge/Topic-LLM%20Security-critical" />

# Recursive Multi-Layer Prompt Defense (RecurDefend)

**경량화된 재귀적 CoT 기반 LLaMA 3 에이전트 심층 방어 프레임워크**
*IPI(Indirect Prompt Injection) & Target Deviation 공격 대응을 위한 Tool Call 보안 검증 및 Cross-Correction*

</div>

---

## 📌 소개

LLM 에이전트가 외부 콘텐츠(웹페이지, 문서, 툴 응답 등)를 처리하는 과정에서 발생할 수 있는 **간접 프롬프트 인젝션(IPI)**과 **목표 이탈(Target Deviation)** 공격을 다층으로 방어하는 프레임워크입니다. 입력·출력 각 단계에 경량 검증 계층(LCE, Lightweight Correction/Check Engine)을 두고, Rule 기반과 ML 기반 탐지를 결합해 에이전트의 Tool Call을 검증합니다.

## 🏗️ 아키텍처

```text
사용자 프롬프트
   → 전처리 (preprocess)
   → Input LCE (Rule + ML 기반 1차 검증)
   → Core Model (LLaMA 3 기반 응답 생성)
   → Output LCE (Rule 기반 출력 검증)
   → Orchestrator (결과 집계 및 escalation 판단)
   → 최종 verdict: allow / flag / block
```

- **Input LCE**: 프롬프트 단계에서 룰 기반(`RuleInputLCE`) + 머신러닝 기반(`MLLCE`, DistilBERT 기반) 이중 검증
- **Core Model**: 실제 응답을 생성하는 LLM 래퍼
- **Output LCE**: 생성된 응답에 대한 룰 기반 사후 검증
- **Orchestrator**: 각 LCE의 판정을 집계(aggregate)하고, 위험도가 높을 경우 상위 검증 단계로 escalation
- **Tool Verifier**: 에이전트의 Tool Call 자체에 대한 보안 검증 계층

## 🛠 기술 스택

- **API 서버**: FastAPI, Uvicorn
- **모델/학습**: PyTorch, Transformers, scikit-learn
- **데이터 처리**: pandas, jsonschema, Datasets
- **배포**: Docker, Docker Compose

## 📂 프로젝트 구조

```text
TeamProject/recurdefend/
├── src/
│   ├── app.py                   # FastAPI 엔트리포인트 (/api/v1/ask)
│   ├── core_model.py            # 코어 LLM 래퍼
│   ├── lce/
│   │   ├── input_lce.py         # 룰 기반 입력 검증
│   │   ├── ml_lce.py            # ML 기반 입력 검증 (DistilBERT)
│   │   ├── output_lce.py        # 룰 기반 출력 검증
│   │   └── train_lce.py         # LCE 모델 학습 스크립트
│   ├── orchestrator/
│   │   ├── orchestrator.py      # 판정 집계 및 escalation 로직
│   │   └── policies.py          # 정책 정의
│   ├── tool_verifier/
│   │   └── verifier.py          # Tool Call 보안 검증
│   └── utils/                   # 전처리, 검증, 설정, 로깅
├── data/
│   ├── raw/                     # 원본 공격/정상 프롬프트 데이터
│   ├── processed/                # 전처리된 학습 데이터 (jsonl)
│   └── schemas/                  # 데이터 스키마 정의
├── scripts/                       # 데이터 생성/변환/증강 스크립트
├── docker/                        # Dockerfile, docker-compose
└── requirements.txt
```

## 🚀 Quick Start

```bash
cd TeamProject/recurdefend

# (선택) 가상환경 생성
python -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt

# 데이터 전처리
python src/utils/preprocess.py

# 데이터 유효성 검사
python src/utils/validate.py

# API 서버 실행
uvicorn src.app:app --host 0.0.0.0 --port 8000
```

### API 사용 예시

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "사용자 입력 텍스트", "user_id": "test"}'
```

응답에는 `verdict`(allow/flag/block), `response`, 각 검증 단계의 `evidence`가 포함됩니다.

## 🐳 Docker 실행

```bash
cd TeamProject/recurdefend/docker
docker compose up --build
```

## 🔬 데이터 파이프라인

- `scripts/csv_to_jsonl.py`: CSV 형태의 공격 프롬프트를 jsonl로 변환
- `scripts/mutate_attacks.py`: 공격 프롬프트 변형(augmentation) 생성
- `scripts/generate_benign_with_llm.py`: LLM을 활용한 정상 프롬프트 생성
- `scripts/split_dataset.py`: 학습/검증/테스트 데이터 분할

## 📝 참고

본 프로젝트는 LLM 에이전트 보안(IPI/Target Deviation 방어)을 주제로 한 2인 팀 프로젝트(TeamProject/recurdefend)로 진행되었습니다.
