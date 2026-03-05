"""
app/main.py
───────────
FastAPI application entry point.

Wires together:
  - Lifespan startup / shutdown
  - Structured logging
  - Routers (predefined reports, free-SQL engine)
  - Global exception handlers
  - CORS (locked down for production; open for development)
  - OpenAPI metadata
"""

from __future__ import annotations

# When executed directly via `python app/main.py` the parent directory
# may not be on sys.path, causing `import app` to fail.  Detect that
# situation and add the workspace root automatically before any imports
# that reference the package.
import os
import sys

if __name__ == "__main__" and __package__ is None:
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import predefined, free_sql, ai
from app.core.config import get_settings
from app.models.schemas import HealthResponse

settings = get_settings()

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown hooks) ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "Governed Data Platform starting up [env=%s]", settings.app_env
    )
    yield
    logger.info("Governed Data Platform shutting down.")


# ── Application factory ───────────────────────────────────────────────────────


# ── Platform endpoints (module level) ─────────────────────────────────────────

def root() -> dict[str, str]:
    return {
        "service": "Governed Data Platform API",
        "version": "1.0.0",
        "docs": "/docs",
    }


def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        environment=settings.app_env,
    )


# ── Global exception handler (module level) ─────────────────────────────────

async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please contact support."
        },
    )


# ── Application factory ───────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="Governed Data Platform API",
        description=(
            "Enterprise-grade, role-aware, governed data access layer on top "
            "of Databricks Unity Catalog. All access is authenticated, "
            "validated, and audit-logged."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {
                "name": "Predefined Reports",
                "description": (
                    "Option A – Ultra-secure, hardcoded report endpoints. "
                    "No user-supplied SQL."
                ),
            },
            {
                "name": "Controlled SQL Engine",
                "description": (
                    "Option B – Power-mode SELECT-only engine. "
                    "Validated through 5 security layers before execution."
                ),
            },
            {
                "name": "AI Orchestration",
                "description": (
                    "Stage 3 – Natural Language → SQL → Secure Execution. "
                    "AI output is UNTRUSTED and validated through the full "
                    "5-layer SQL firewall before any execution."
                ),
            },
            {
                "name": "Platform",
                "description": "Health-check and platform meta-endpoints.",
            },
        ],
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    if settings.app_env == "development":
        allow_origins = ["*"]
    else:
        # Production: lock down to known frontend origins.
        allow_origins = []  # TODO: add production frontend URL(s)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(predefined.router)
    app.include_router(free_sql.router)
    app.include_router(ai.router)          # Stage 3: /ask

    # register platform endpoints and handler
    app.get(
        "/",
        tags=["Platform"],
        summary="Root",
        include_in_schema=False,
    )(root)

    app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Platform"],
        summary="Health Check",
    )(health_check)

    app.add_exception_handler(Exception, unhandled_exception_handler)

    return app


# ── Application singleton ─────────────────────────────────────────────────────
app = create_app()


if __name__ == "__main__":
    # allow running the app directly with `python app/main.py` or
    # `python -m app.main` during development
    import uvicorn  # imported here to avoid a hard dependency at import time

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
