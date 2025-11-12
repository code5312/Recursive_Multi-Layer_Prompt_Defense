1. 목적 (Purpose)

이 문서는 RecurDefend 프레임워크 내부의 모듈 간 입출력 구조(Interface Contract) 를 표준화하기 위한 개발자 가이드다.
각 모듈은 독립적으로 교체·테스트 가능해야 하며, 공통된 I/O 형태를 준수해야 한다.

2. 전체 파이프라인 개요
┌───────────────────────────┐
│       Input LCE           │  ← 입력 인젝션 탐지 (Rule + DistilBERT)
└────────────┬──────────────┘
             │
┌────────────▼──────────────┐
│    Recursive CoT Controller│  ← 재귀적 추론 + 스텝 검증
└────────────┬──────────────┘
             │
┌────────────▼──────────────┐
│       Tool Verifier       │  ← 툴 호출/파라미터/권한 검증
└────────────┬──────────────┘
             │
┌────────────▼──────────────┐
│     Cross-Correction      │  ← 입력-출력 의도 정렬
└────────────┬──────────────┘
             │
┌────────────▼──────────────┐
│       Output LCE          │  ← 출력 정책 위반/정보 유출 탐지
└────────────┴──────────────┘

3. 공통 타입 (Base Data Structures)
3.1 Request Object
@dataclass
class OrchestratorRequest:
    id: str
    user_text: str
    context_html: Optional[str]
    tools_allowed: List[str]
    opts: Dict[str, Any]

3.2 Response Object
@dataclass
class OrchestratorResponse:
    id: str
    status: str            # "ok" | "blocked" | "repaired"
    answer: Optional[str]
    meta: Dict[str, Any]

3.3 Generic Prediction Result
Prediction = Dict[str, Any]  # {'score': float, 'label': str, 'signals': Dict}

4. 모듈별 인터페이스
4.1 Input LCE (Lightweight Counter-Exploit)
항목	내용
파일 위치	src/lce/input_lce.py
주요 기능	사용자 입력(user_text, context_html)에서 IPI 및 오염 패턴 탐지
입력	{"text": str, "html": Optional[str]}
출력	`{"score": float, "label": "safe"
예시
{
  "score": 0.82,
  "label": "risk",
  "signals": {
    "hidden_css": 1,
    "meta_prompt": 1,
    "zero_width_space": 0
  }
}

예외 처리

입력이 None 또는 문자열 외 타입이면 ValueError

모델 예측 실패 시 RuntimeError("input_lce failure")

4.2 Recursive CoT Controller
항목	내용
파일 위치	src/recursive_cot/controller.py
주요 기능	모델의 reasoning trace를 step-by-step으로 생성하고 각 step을 검증·롤백
입력	prompt: str, context_html: Optional[str]
출력	{"final_text": str, "trace": [step], "rolled_back": bool, "tool_calls": [dict]}
step 구조 예시
{
  "index": 3,
  "text": "To summarize the HTML, I'll extract visible text...",
  "validated": true,
  "risk_score": 0.15,
  "tool_call": null
}

예외 처리

step 검증 실패 시 rollback 수행, trace 유지

내부 timeout 시 "rolled_back": true로 반환

4.3 Tool Verifier
항목	내용
파일 위치	src/tool_verifier/verifier.py
주요 기능	함수 호출 시 파라미터·권한·레이트리밋 검사
입력	{"name": str, "args": dict, "caller": str}
출력	{"allow": bool, "reason": str, "patched_args": Optional[dict]}
예시
{
  "allow": false,
  "reason": "schema_mismatch",
  "patched_args": {"units": "metric"}
}

정책 위반 처리

deny_on_schema_mismatch: true → allow=false

rate_limit_fallback: true → 호출 차단 대신 fallback safe value 적용

4.4 Cross-Correction Aligner
항목	내용
파일 위치	src/cross_correction/aligner.py
주요 기능	입력 intent와 출력 goal의 불일치 탐지 및 교정 수행
입력	intent_in: dict, text_out: str, trace: list
출력	`{"status": "ok"
예시
{
  "status": "repaired",
  "output": "요약 요청에 맞춰 페이지 내용을 정리했습니다."
}

교정 전략

"re_prompt": 새로운 제약 프롬프트로 재생성

"constrained_gen": Safe Token Filtering 적용

"reinforce": LCE scoring feedback 기반 재시도

4.5 Output LCE
항목	내용
파일 위치	src/lce/output_lce.py
주요 기능	최종 출력에서 목표 변질·정보 유출·정책 위반 탐지
입력	text: str
출력	`{"score": float, "label": "safe"
예시
{
  "score": 0.91,
  "label": "risk",
  "signals": {
    "secret_leak": 1,
    "policy_violation": 1,
    "objective_shift": 0
  }
}

5. Orchestrator (Main Pipeline Coordinator)
항목	내용
파일 위치	src/orchestrator/orchestrator.py
주요 기능	전체 단계 순서 제어, 이벤트 로그 기록, 상태머신 관리
입력	OrchestratorRequest
출력	OrchestratorResponse
에러 처리	단계별 예외를 status="blocked" 형태로 래핑하여 반환
함수 시그니처
def process(self, req: OrchestratorRequest) -> OrchestratorResponse:
    ...

6. 공통 로깅 포맷 (Event Log Contract)

모든 모듈은 src/io/logging.py의 log.event()를 호출하여 표준 이벤트 구조를 남긴다.

log.event(
    qid=req.id,
    stage="input_lce",
    decision="pass",
    score=0.12,
    payload={"signals": {"hidden_css": 0}},
    latency_ms=10.4
)


스키마 검증: data/schemas/eventlog.schema.json

민감정보: LCE/Verifier 단계에서 마스킹 후 기록

7. 상태 코드 정의 (Status Codes)
상태	설명
ok	정상 종료, 수정 불필요
repaired	불일치·오염 교정 후 성공
blocked	위험 탐지 또는 정책 위반으로 중단

8. 예외/에러 계약 (Error Contract)

모든 모듈은 예외 발생 시 다음 형식을 사용한다.

{
  "error": {
    "code": "E001",
    "module": "input_lce",
    "message": "Model timeout"
  }
}

코드	모듈	의미
E001	any	모델 응답 지연(timeout)
E002	input_lce	입력 구조 오류
E003	recursive_cot	reasoning trace 손상
E004	tool_verifier	스키마 검증 실패
E005	cross_correction	intent parser 실패
E006	output_lce	출력 스코어 계산 실패

9. 테스트 표준 (Module Validation Checklist)
항목	체크포인트
Input LCE	규칙/모델 병합 스코어 검증
Recursive CoT	step rollback 정상 동작
Tool Verifier	툴 미등록/권한 위반 처리
Cross-Correction	intent mismatch → 재교정 성공률
Output LCE	leak/violation 시 차단 확률

10. 확장 규칙

각 모듈은 BaseInterface 클래스(src/utils/interfaces.py)를 상속받을 수 있다.

새로운 LCE 변형, 추가 verifier 등을 도입할 경우 기존 key/value 구조 호환성 유지.

새로운 필드는 반드시 additionalProperties: true 조건을 유지하도록 설계.

11. 요약
모듈	입력	출력	역할
Input LCE	text, html	score, label, signals	입력 오염 감지
Recursive CoT	prompt	final_text, trace, rolled_back	단계별 검증/롤백
Tool Verifier	tool call	allow, reason, patched_args	툴 파라미터 검증
Cross-Correction	intent_in, text_out	status, output	의도 정렬/교정
Output LCE	text	score, label, signals	출력 정책 검증
Orchestrator	전체 req	status, answer	통합 제어