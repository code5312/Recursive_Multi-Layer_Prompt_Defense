# src/service/routers.py
# FastAPI Routers for RecurDefend
# - /v1/agent/query
# - /v1/logs/{id}
# - /v1/evaluate/run, /v1/evaluate/results/{job_id}
# - /v1/tools
# - /healthz, /version

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError

from src.service.schemas import (
    AgentQueryRequest,
    WrappedAgentQueryResponse,
    AgentQueryResponseData,
    WrappedEventLogResponse,
    EventLogList,
    WrappedEvaluateRunResponse,
    EvaluateRunRequest,
    EvaluateRunAccepted,
    WrappedEvaluateResultsResponse,
    EvaluateResultsData,
    WrappedToolsResponse,
    ToolsList,
    ToolSummary,
    WrappedHealthResponse,
    HealthData,
    WrappedVersionResponse,
    VersionData,
    ErrorResponse,
    ErrorBody,
)
from src.orchestrator.orchestrator import Orchestrator, OrchestratorRequest as OrcReq


# ---------------------------
# Dependencies & Utilities
# ---------------------------

def _get_orchestrator(request: Request) -> Orchestrator:
    orch: Optional[Orchestrator] = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    return orch

def _request_id(request: Request) -> str:
    # X-Request-ID 우선, 없으면 생성
    rid = request.headers.get("X-Request-ID")
    return rid or str(uuid.uuid4())

def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()

def _ok(data: Any, request_id: str, duration_ms: Optional[float] = None) -> Dict[str, Any]:
    return {"ok": True, "data": data, "meta": {"request_id": request_id, "duration_ms": duration_ms}}

def _err(code: str, message: str, request_id: str, details: Optional[Dict[str, Any]] = None, status_code: int = 400):
    body = ErrorResponse(ok=False, error=ErrorBody(code=code, message=message, details=details), meta={"request_id": request_id})
    raise HTTPException(status_code=status_code, detail=body.dict())


# ---------------------------
# Router
# ---------------------------

router = APIRouter(prefix="/v1", tags=["recurdefend"])


# 1) 메인 파이프라인
@router.post("/agent/query", response_model=WrappedAgentQueryResponse)
async def agent_query(request: Request, payload: AgentQueryRequest, orchestrator: Orchestrator = Depends(_get_orchestrator)):
    rid = _request_id(request)
    qid = payload.id or str(uuid.uuid4())

    # Orchestrator 요청 변환
    orc_req = OrcReq(
        id=qid,
        user_text=payload.user_text,
        context_html=payload.context_html,
        tools_allowed=payload.tools_allowed or [],
        opts=(payload.opts.dict() if payload.opts else {}),
    )

    # 처리
    resp = orchestrator.process(orc_req)

    # 래핑
    data = AgentQueryResponseData(id=resp.id, status=resp.status, answer=resp.answer, meta=resp.meta)
    return _ok(data=data.dict(), request_id=rid)


# 2) 이벤트 로그 조회
@router.get("/logs/{qid}", response_model=WrappedEventLogResponse)
async def get_logs(request: Request, qid: str, format: str = Query("json", regex="^(json|jsonl)$"), limit: int = Query(1000, ge=1, le=100000)):
    rid = _request_id(request)
    store: Dict[str, List[Dict[str, Any]]] = getattr(request.app.state, "log_store", {})
    events = store.get(qid, [])
    if not events:
        # 404 대신 빈 목록을 반환해도 되지만 계약상 404가 더 분명
        raise HTTPException(status_code=404, detail=f"No events for qid={qid}")

    # limit 적용
    events = events[:limit]

    if format == "jsonl":
        # jsonl를 그대로 반환하려면 StreamingResponse가 좋지만, 계약 모델은 json이므로 안내
        # 여기서는 json 배열로 반환 (필요시 별도 엔드포인트로 streaming 지원)
        pass

    try:
        elist = EventLogList(qid=qid, events=events)  # validate pydantic
    except ValidationError as ve:
        raise HTTPException(status_code=500, detail=f"Event log validation failed: {ve}")

    return _ok(data=elist.dict(), request_id=rid)


# 3) 배치 평가 실행(내부)
@router.post("/evaluate/run", response_model=WrappedEvaluateRunResponse)
async def evaluate_run(request: Request, payload: EvaluateRunRequest):
    rid = _request_id(request)
    job_id = f"eval-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    jobs: Dict[str, Dict[str, Any]] = getattr(request.app.state, "eval_jobs", {})
    # 단순히 큐잉된 것처럼 등록 (데모/스텁). 실제 구현은 워커에서 처리.
    jobs[job_id] = {
        "status": "queued",
        "params": payload.dict(),
        "created_at": _utcnow_iso(),
        "metrics": None,
        "artifacts": None,
    }
    request.app.state.eval_jobs = jobs

    data = EvaluateRunAccepted(job_id=job_id, status="accepted", results_uri=f"/v1/evaluate/results/{job_id}")
    return _ok(data=data.dict(), request_id=rid)


# 4) 평가 결과 조회(내부)
@router.get("/evaluate/results/{job_id}", response_model=WrappedEvaluateResultsResponse)
async def evaluate_results(request: Request, job_id: str):
    rid = _request_id(request)
    jobs: Dict[str, Dict[str, Any]] = getattr(request.app.state, "eval_jobs", {})
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job_id={job_id}")

    # 데모용: 큐잉 상태면 즉석에서 완료 상태로 전이시켜준다(스텁)
    if job["status"] in ("queued", "running"):
        job["status"] = "done"
        job["metrics"] = {
            "precision": 0.93,
            "recall": 0.91,
            "f1_score": 0.92,
            "bypass_rate": 0.08,
            "alignment_success_rate": 0.87,
            "latency_ms": 655.0,
        }
        job["artifacts"] = {
            "table": "/results/tables/demo.json",
            "figures": ["/results/figures/pr_curve.png", "/results/figures/roc_curve.png"],
            "cases": "/results/case_studies/demo.html",
        }
        jobs[job_id] = job
        request.app.state.eval_jobs = jobs

    data = EvaluateResultsData(
        job_id=job_id,
        status=job["status"],
        metrics=job.get("metrics"),
        artifacts=job.get("artifacts"),
    )
    return _ok(data=data.dict(), request_id=rid)


# 5) 툴 레지스트리 조회
@router.get("/tools", response_model=WrappedToolsResponse)
async def list_tools(request: Request):
    rid = _request_id(request)
    toolspec_path = os.getenv("RECURDEFEND_TOOLSPECS", "data/raw/toolspecs.json")
    if not os.path.exists(toolspec_path):
        # 빈 목록
        data = ToolsList(tools=[], count=0)
        return _ok(data=data.dict(), request_id=rid)

    try:
        with open(toolspec_path, "r", encoding="utf-8") as f:
            content = json.load(f)
    except Exception as e:
        _err("E004", f"Failed to read toolspecs.json: {e}", request_id=rid, status_code=500)

    # content가 단일 오브젝트 혹은 리스트일 수 있다고 가정 — 리스트로 정규화
    entries: List[Dict[str, Any]] = content if isinstance(content, list) else [content]
    summaries: List[ToolSummary] = []
    for ent in entries:
        try:
            summaries.append(
                ToolSummary(
                    name=ent.get("name", "unknown"),
                    version=ent.get("version"),
                    min_role=ent.get("policy", {}).get("min_role"),
                )
            )
        except ValidationError:
            # 유효하지 않은 항목은 스킵
            continue

    data = ToolsList(tools=summaries, count=len(summaries))
    return _ok(data=data.dict(), request_id=rid)


# 6) 헬스 & 버전(루트 레벨로도 접근 필요하여 별도 라우터가 app에서 마운트됨)
health_router = APIRouter(tags=["meta"])

@health_router.get("/healthz", response_model=WrappedHealthResponse)
async def healthz():
    return _ok(data=HealthData(status="healthy").dict(), request_id=str(uuid.uuid4()))

@health_router.get("/version", response_model=WrappedVersionResponse)
async def version(request: Request):
    semver = getattr(request.app.state, "semver", "1.0.0")
    gitsha = getattr(request.app.state, "gitsha", None)
    return _ok(data=VersionData(api="v1", semver=semver, git=gitsha).dict(), request_id=str(uuid.uuid4()))
