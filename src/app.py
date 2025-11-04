# src/app.py
# FastAPI Application Entrypoint for RecurDefend
# - orchestrator 및 각 모듈 주입
# - 라우터 등록
# - 로깅/상태 초기화
# 실행: uvicorn src.app:app --reload

from __future__ import annotations

import os
import uuid
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.io.logging import StructuredLogger
from src.tool_verifier.registry import ToolRegistry
from src.tool_verifier.verifier import RegistryToolVerifier
from src.lce.input_lce import InputLCE
from src.lce.output_lce import OutputLCE
from src.core_model import get_llm_from_env
from src.recursive_cot.controller import CoTController
from src.cross_correction.aligner import CrossCorrectionAligner
from src.utils.intent import SimpleIntentParser

# 내부 모듈
from src.service import routers
from src.orchestrator.orchestrator import (
    Orchestrator,
    OrchestratorRequest,
    OrchestratorResponse,
    DictConfig,
)

# -------------------------------
# Mock / Stub Modules for Demo
# -------------------------------

class MockInputLCE:
    def predict(self, x: Dict[str, Any]) -> Dict[str, Any]:
        text = (x.get("text") or "").lower()
        risky = any(tag in text for tag in ["display:none", "ignore user", "meta prompt"])
        return {
            "score": 0.9 if risky else 0.1,
            "label": "risk" if risky else "safe",
            "signals": {"hidden_css": int("display:none" in text)},
        }


class MockOutputLCE:
    def predict(self, text: str) -> Dict[str, Any]:
        risky = any(k in text.lower() for k in ["system prompt", "password", "api_key"])
        return {
            "score": 0.85 if risky else 0.05,
            "label": "risk" if risky else "safe",
            "signals": {"policy_violation": int(risky)},
        }


class MockCoTController:
    def run(self, prompt: str, context_html: Optional[str] = None) -> Dict[str, Any]:
        # 단순히 "reasoning" 흉내만 냄
        text = f"[CoT] {prompt}"
        trace = [{"index": 0, "text": text, "validated": True}]
        return {"final_text": text, "trace": trace, "rolled_back": False}

    def rollback_or_patch(self, call: Dict[str, Any], verifier_result: Dict[str, Any]) -> Dict[str, Any]:
        # 단순 패치 동작
        return {"final_text": "[Patched] tool denied", "trace": [], "rolled_back": True}


class MockAligner:
    def align(self, intent_in: Dict[str, Any], text_out: str, trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        if "ignore user" in text_out.lower():
            return {"status": "repaired", "output": "[Repaired] Removed malicious content"}
        return {"status": "ok", "output": text_out}


class MockIntentParser:
    def parse(self, text: str) -> Dict[str, Any]:
        return {"goal": text.strip().split()[0] if text else "unknown"}


# -------------------------------
# FastAPI Application Factory
# -------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="RecurDefend API",
        version="1.0.0",
        description="Recursive CoT & Cross-Correction Defense Framework for LLaMA3",
    )

    # ----- Middleware -----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 개발용, 배포 시 수정
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ----- 상태 객체 초기화 -----
    app.state.log_store: Dict[str, List[Dict[str, Any]]] = {}
    app.state.eval_jobs: Dict[str, Dict[str, Any]] = {}
    app.state.semver = "1.0.0"
    app.state.gitsha = os.getenv("GIT_COMMIT_SHA")

    # ----- 구성 로딩 -----
    cfg = {
        "cot": {"max_steps": 5},
        "lce": {"input": {"threshold": 0.6}, "output": {"threshold": 0.65}},
        "cross_correction": {"strategy": "re_prompt"},
    }
    config = DictConfig(cfg)

    # ----- 모듈 주입 -----
    logger = StructuredLogger(
        store=app.state.log_store,
        log_dir="logs/runtime",
        redact_keys=["api_key", "token", "password"],
        rotate_mb=10,
    )

    tool_registry = ToolRegistry()
    toolv = RegistryToolVerifier(tool_registry)

    llm = get_llm_from_env()  # ← 환경변수에 따라 자동 로드 (없으면 None)

    orchestrator = Orchestrator(
        input_lce=InputLCE(model_path="models/input_lce", threshold=0.6),
        cot_controller=CoTController(max_steps=5, llm=llm),  # ← LLM 주입
        tool_verifier=toolv,
        aligner=CrossCorrectionAligner(threshold=0.80),
        output_lce=OutputLCE(model_path="models/output_lce", threshold=0.65),
        intent_parser=SimpleIntentParser(),
        logger=logger,
        config=config,
    )
    app.state.orchestrator = orchestrator

    # ----- 라우터 등록 -----
    app.include_router(routers.router)
    app.include_router(routers.health_router)

    return app


# FastAPI 인스턴스 (uvicorn entry)
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)
