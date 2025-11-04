# src/service/schemas.py
# RecurDefend API Pydantic Schemas
# - 요청/응답 본문 규격
# - 이벤트 로그 구조
# - 배치 평가 I/O
# Contracts 참조: contracts/API.md, data/schemas/*.json

from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, root_validator, validator, constr, conint, confloat


# -----------------------------
# Common / Envelope
# -----------------------------

class MetaEnvelope(BaseModel):
    request_id: Optional[str] = Field(default=None, description="서버가 생성/전달하는 요청 추적 ID")
    duration_ms: Optional[confloat(ge=0)] = Field(default=None, description="서버 처리 소요(ms)")


class ErrorBody(BaseModel):
    code: constr(strip_whitespace=True, min_length=1) = Field(..., description="에러 코드 (E00X)")
    message: constr(strip_whitespace=True, min_length=1) = Field(..., description="사유/메시지")
    details: Optional[Dict[str, Any]] = Field(default=None, description="부가 정보(필드/상태 등)")


class ErrorResponse(BaseModel):
    ok: Literal[False] = False
    error: ErrorBody
    meta: Optional[MetaEnvelope] = None


# -----------------------------
# Agent Query (Main Pipeline)
# -----------------------------

class AgentQueryOpts(BaseModel):
    max_cot_steps: Optional[conint(ge=1, le=20)] = Field(default=5, description="Recursive CoT 최대 스텝")
    class Config:
        extra = "allow"   # 추가 옵션 확장 허용


class AgentQueryRequest(BaseModel):
    id: Optional[str] = Field(default=None, description="클라이언트 제공 ID(없으면 서버가 생성)")
    user_text: constr(min_length=1, max_length=10_000) = Field(..., description="사용자 질의")
    context_html: Optional[str] = Field(default=None, description="외부 HTML 컨텍스트(옵션)")
    tools_allowed: Optional[List[constr(min_length=1)]] = Field(default=None, description="허용 툴 목록 (중복 불가)")
    opts: Optional[AgentQueryOpts] = None

    @validator("context_html")
    def _normalize_empty_html(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @root_validator
    def _unique_tools(cls, values):
        tools = values.get("tools_allowed")
        if tools:
            if len(tools) != len(set(tools)):
                raise ValueError("tools_allowed 항목은 고유해야 합니다(중복 불가).")
        return values


AgentStatus = Literal["ok", "blocked", "repaired"]


class AgentQueryResponseData(BaseModel):
    id: str
    status: AgentStatus
    answer: Optional[str] = Field(default=None, description="최종 응답(차단 시 null)")
    meta: Dict[str, Any] = Field(
        ...,
        description="추가 메타데이터(rolled_back, reason, events_uri, latency_ms 등)"
    )


class WrappedAgentQueryResponse(BaseModel):
    ok: Literal[True] = True
    data: AgentQueryResponseData
    meta: Optional[MetaEnvelope] = None


# -----------------------------
# Event Log
# -----------------------------

LogStage = Literal[
    "input_lce",
    "recursive_cot_step",
    "tool_verify",
    "cross_correction",
    "output_lce",
]

LogDecision = Optional[Literal["allow", "deny", "rollback", "repair", "pass"]]


class ModelInfo(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class EventPayload(BaseModel):
    # 유연성 확보: 추가 키 허용 (signals/reason/patched_args/rolled_back 등)
    signals: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    patched_args: Optional[Dict[str, Any]] = None
    rolled_back: Optional[bool] = None

    class Config:
        extra = "allow"


class EventLogEntry(BaseModel):
    qid: constr(min_length=8)
    timestamp: datetime
    stage: LogStage
    decision: LogDecision = None
    score: Optional[float] = None
    latency_ms: Optional[confloat(ge=0)] = None
    trace_id: Optional[int] = Field(default=None, description="질의 내 순서 추적용 증가 번호")
    step_index: Optional[conint(ge=0)] = None
    tool_name: Optional[str] = None
    anonymized: bool = Field(default=True, description="민감정보 마스킹 여부")
    model_info: Optional[ModelInfo] = None
    policy_flags: Optional[Dict[str, Any]] = Field(default=None, description="정책 스냅샷(선택)")
    error: Optional[ErrorBody] = None
    payload: EventPayload

    class Config:
        extra = "forbid"


class EventLogList(BaseModel):
    qid: str
    events: List[EventLogEntry]


class WrappedEventLogResponse(BaseModel):
    ok: Literal[True] = True
    data: EventLogList
    meta: Optional[MetaEnvelope] = None


# -----------------------------
# Evaluate (Batch)
# -----------------------------

class EvaluateRunRequest(BaseModel):
    experiment: constr(min_length=1) = Field(..., description="실험 식별자")
    dataset_path: constr(min_length=1) = Field(..., description="데이터셋 경로 (예: data/processed/test.jsonl)")
    config_path: Optional[str] = Field(default=None, description="실험 설정 경로 (예: configs/experiments/exp.yaml)")
    limit: Optional[conint(ge=1)] = Field(default=None, description="평가 상한 개수")


class EvaluateRunAccepted(BaseModel):
    job_id: str
    status: Literal["accepted"] = "accepted"
    results_uri: Optional[str] = Field(default=None, description="결과 조회 URI")


class WrappedEvaluateRunResponse(BaseModel):
    ok: Literal[True] = True
    data: EvaluateRunAccepted
    meta: Optional[MetaEnvelope] = None


class EvaluateArtifacts(BaseModel):
    table: Optional[str] = None
    figures: Optional[List[str]] = None
    cases: Optional[str] = None


class EvaluateMetrics(BaseModel):
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    bypass_rate: Optional[float] = None
    alignment_success_rate: Optional[float] = None
    latency_ms: Optional[float] = None


class EvaluateResultsData(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    metrics: Optional[EvaluateMetrics] = None
    artifacts: Optional[EvaluateArtifacts] = None


class WrappedEvaluateResultsResponse(BaseModel):
    ok: Literal[True] = True
    data: EvaluateResultsData
    meta: Optional[MetaEnvelope] = None


# -----------------------------
# Tools Listing
# -----------------------------

class ToolSummary(BaseModel):
    name: str
    version: Optional[str] = None
    min_role: Optional[Literal["guest", "user", "admin"]] = None


class ToolsList(BaseModel):
    tools: List[ToolSummary]
    count: int


class WrappedToolsResponse(BaseModel):
    ok: Literal[True] = True
    data: ToolsList
    meta: Optional[MetaEnvelope] = None


# -----------------------------
# Health / Version
# -----------------------------

class HealthData(BaseModel):
    status: Literal["healthy", "degraded", "down"] = "healthy"


class WrappedHealthResponse(BaseModel):
    ok: Literal[True] = True
    data: HealthData
    meta: Optional[MetaEnvelope] = None


class VersionData(BaseModel):
    api: str = Field(..., description="API 버전 prefix (예: v1)")
    semver: str = Field(..., description="SemVer 문자열 (예: 1.0.0)")
    git: Optional[str] = Field(default=None, description="git sha 또는 태그")


class WrappedVersionResponse(BaseModel):
    ok: Literal[True] = True
    data: VersionData
    meta: Optional[MetaEnvelope] = None
