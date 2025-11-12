# src/app.py

from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .utils.config import load_config
from .io.logging import StructuredLogger
from .tool_verifier.registry import ToolRegistry
from .tool_verifier.verifier import RegistryToolVerifier
from .core_model import get_llm_from_env
from .recursive_cot.controller import CoTController
from .cross_correction.aligner import CrossCorrectionAligner
from .lce.input_lce import InputLCE
from .lce.output_lce import OutputLCE
from .utils.intent import SimpleIntentParser
from .service import routers
from .orchestrator.orchestrator import Orchestrator, DictConfig


def create_app() -> FastAPI:
    # ----- 구성 로딩 (항상 dict 보장) -----
    try:
        loaded = load_config()
        if isinstance(loaded, dict):
            cfg: Dict[str, Any] = loaded
        else:
            cfg = {}
    except Exception as e:
        print(f"[WARN] Failed to load config, using defaults: {e}")
        cfg = {}

    # 필요하다면 DictConfig 래핑 (or 그냥 cfg 그대로 사용)
    config = DictConfig(cfg)

    # ----- FastAPI 인스턴스 -----
    app = FastAPI(
        title=cfg.get("app.name", "RecurDefend API"),
        version=cfg.get("app.version", "1.0.0"),
        description=cfg.get(
            "app.description",
            "Recursive CoT & Cross-Correction Defense Framework for LLaMA3",
        ),
    )

    # CORS (dev 용)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ----- 상태 객체 초기화 -----
    app.state.log_store: Dict[str, List[Dict[str, Any]]] = {}
    app.state.eval_jobs: Dict[str, Dict[str, Any]] = {}
    app.state.semver = cfg.get("app.semver", "1.0.0")
    app.state.gitsha = os.getenv("GIT_COMMIT_SHA")
    app.state.config = cfg

    # ----- 로거 -----
    logger = StructuredLogger(
        store=app.state.log_store,
        log_dir=cfg.get("logging.log_dir", "logs/runtime"),
        redact_keys=cfg.get(
            "logging.redact_keys",
            ["api_key", "token", "password"],
        ),
        rotate_mb=cfg.get("logging.rotate_mb", 10),
    )

    # ----- Tool Registry & Verifier -----
    toolspecs_path = cfg.get("tools.specs_path", "data/raw/toolspecs.json")
    os.environ.setdefault("RECURDEFEND_TOOLSPECS", toolspecs_path)

    tool_registry = ToolRegistry()
    toolv = RegistryToolVerifier(tool_registry)

    # ----- LLM 클라이언트 (Stub 포함) -----
    llm = get_llm_from_env()  # 환경 없으면 StubLLM 리턴하도록 core_model.py 수정해둔 상태 기준

    # ----- Orchestrator -----
    orchestrator = Orchestrator(
        input_lce=InputLCE(
            model_path=cfg.get("lce.input.model_path", "models/input_lce"),
            threshold=float(cfg.get("lce.input.threshold", 0.60)),
        ),
        cot_controller=CoTController(
            max_steps=int(cfg.get("cot.max_steps", 5)),
            llm=llm,
        ),
        tool_verifier=toolv,
        aligner=CrossCorrectionAligner(
            threshold=float(cfg.get("cross_correction.threshold", 0.80)),
        ),
        output_lce=OutputLCE(
            model_path=cfg.get("lce.output.model_path", "models/output_lce"),
            threshold=float(cfg.get("lce.output.threshold", 0.65)),
        ),
        intent_parser=SimpleIntentParser(),
        logger=logger,
        config=config,  # 또는 cfg; Orchestrator 시그니처에 맞춰 선택
    )
    app.state.orchestrator = orchestrator

    # ----- 라우터 등록 -----
    app.include_router(routers.router)
    app.include_router(routers.health_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)
