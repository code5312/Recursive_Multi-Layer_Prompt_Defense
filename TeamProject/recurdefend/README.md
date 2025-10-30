# RecurDefend
경량화된 재귀적 CoT 기반 LLaMA 3 에이전트 심층 방어 프레임워크  
_Subtitle:_ IPI & Target Deviation 공격 대응을 위한 Tool Call 보안 검증 및 Cross-Correction

## Quick Start
```bash
# (선택) 가상환경
pip install -r requirements.txt

# 데이터 전처리
python src/utils/preprocess.py

# 유효성 검사
python src/utils/validate.py

# API 서버 실행
uvicorn src.app:app --host 0.0.0.0 --port 8000
