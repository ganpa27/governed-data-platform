"""
app/api/ai.py
─────────────
Stage 3 – AI Orchestration Endpoint (Enhanced with Intent Router)

POST /ask  →  Natural Language → [Intent Router] → Predefined API  (preferred)
                                                 ↘ SQL Generation     (fallback)

Full execution pipeline (updated):

  Step 1  Extract & resolve user identity          (get_current_user)
  Step 2  Route question to predefined API         (intent_router.route_question)
          → If matched: execute predefined SQL, skip to Step 8
          → If no match: fall through to LLM path (Step 3)
  Step 3  Call AI service → raw SQL string         (ai_orchestrator.generate_sql)
  Step 4  Pass SQL through existing 5-layer validator  (validator.validate_query)
  Step 5  If validation fails → audit BLOCKED → return 403
  Step 6  Inject LIMIT if missing                  (ai_orchestrator.inject_limit)
  Step 7  Audit BEFORE execution                   (audit.log_event)
  Step 8  Execute in Databricks                    (database.execute_query)  [if LLM path]
  Step 9  Audit AFTER execution with timing + row count
  Step 10 Return AskResponse

WHY THIS DESIGN:
  Predefined routes are the safest possible execution path — no LLM output,
  no raw SQL generation, zero hallucination risk. By routing matching questions
  to predefined APIs first, we:
    1. Reuse all the secure, audited query logic already built in predefined.py
    2. Make the system expandable — new predefined report = new AI capability
    3. Reserve LLM SQL generation only for truly novel/complex questions
    4. The AI is NEVER trusted when a predefined route exists

Error mapping (per §9):
  LLM failure         → 503  Service Unavailable
  AI refuses question → 400  Bad Request
  SQL invalid         → 403  Forbidden  (governance block)
  Execution error     → 502  Bad Gateway
  No data             → 200  (empty list, NOT an error)

AI is NOT trusted.  The validator is the gatekeeper.
The intent router is the fast-path.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import execute_query
from app.core.security import get_current_user
from app.models.schemas import AskRequest, AskResponse, UserContext
from app.services import ai_orchestrator
from app.services.ai_orchestrator import AIServiceError
from app.services.audit import log_ai_event
from app.services.intent_router import route_question, list_registered_routes
from app.services.validator import ValidationError, validate_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Orchestration"])
print("AI router loaded")  # debug print to confirm router is registered


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Natural Language Query (AI-Governed)",
    description=(
        "Ask a question in plain English. "
        "The system FIRST attempts to match your question to an existing "
        "predefined secure report (zero SQL generation, maximum safety). "
        "If no predefined route matches, the backend translates the question "
        "to SQL using an LLM, validates through the 5-layer SQL firewall, "
        "and executes against secure governed views only. "
        "The AI is NEVER trusted — the validator is the gatekeeper."
    ),
    responses={
        400: {"description": "AI cannot answer this question with available data."},
        403: {"description": "AI-generated SQL blocked by governance validator."},
        503: {"description": "LLM provider unavailable."},
        502: {"description": "Databricks execution failure."},
    },
)
def ask_question(
    payload: AskRequest,
    current_user: Annotated[UserContext, Depends(get_current_user)],
) -> AskResponse:
    """
    AI-governed NL→SQL→Execution endpoint with Intent Router.

    Preferred path: question → predefined API (no LLM call, maximum safety).
    Fallback path:  question → LLM → validate → execute (for novel questions).
    Every step is logged; a blocked or failed query NEVER silently passes.
    """
    print("Received /ask request with question:", payload.question)
    question = payload.question
    t_start = time.perf_counter()

    # ── Step 1: User already resolved by get_current_user() ───────────────────

    # ── Step 2: Try routing to a predefined API first ─────────────────────────
    #
    # This is the new "Intent Router" step. Instead of always calling the LLM,
    # we first check if the question matches a known predefined report.
    # This is:
    #   - Faster (no LLM API call)
    #   - Safer  (no raw SQL generation)
    #   - Cheaper (no API tokens consumed)
    #   - More reliable (predefined queries never hallucinate)
    #
    try:
        route_result = route_question(
            question=question,
            user_role=current_user.role_name,
        )
    except Exception as exc:
        # Intent router failure is non-fatal — fall through to LLM path
        logger.warning(
            "[AI] Intent router error (falling back to LLM): %s", exc
        )
        route_result = None

    if route_result is not None and route_result.matched:
        # ──────────────────────────────────────────────────────────────────────
        # PREDEFINED PATH: Question matched a registered intent route.
        # We execute the predefined SQL directly — no LLM involved.
        # ──────────────────────────────────────────────────────────────────────
        elapsed_ms = _elapsed(t_start)
        logger.info(
            "[AI] Predefined route matched: route=%s view=%s user=%s",
            route_result.route_name,
            route_result.view_name,
            current_user.email,
        )

        # Audit the predefined-path execution
        _audit_ai(
            user=current_user,
            question=question,
            generated_sql=f"[PREDEFINED_ROUTE:{route_result.route_name}] {route_result.sql_executed}",
            accessed_object=route_result.view_name or "unknown",
            status="success_predefined",
            elapsed_ms=elapsed_ms,
            row_count=len(route_result.data),
        )

        return AskResponse(
            status="success",
            question=question,
            sql_generated=route_result.sql_executed or "",
            rows_returned=len(route_result.data),
            data=route_result.data,
            accessed_object=route_result.view_name or "unknown",
            execution_time_ms=round(elapsed_ms, 2),
            execution_timestamp=datetime.utcnow(),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # LLM FALLBACK PATH: No predefined route matched — call the LLM.
    # This handles novel or complex questions not covered by predefined reports.
    # ──────────────────────────────────────────────────────────────────────────
    logger.info(
        "[AI] No predefined route matched — using LLM for user=%s question='%s'",
        current_user.email,
        question[:80],
    )

    # ── Step 3: Call AI service → get raw SQL ─────────────────────────────────
    try:
        raw_sql = ai_orchestrator.generate_sql(
            question=question,
            user_role=current_user.role_name,
        )
    except ValueError as exc:
        # AI returned CANNOT_ANSWER → not a server error, it's a bad question
        logger.warning(
            "[AI] Cannot answer question for user=%s: %s",
            current_user.email,
            exc,
        )
        _audit_ai(
            user=current_user,
            question=question,
            generated_sql="CANNOT_ANSWER",
            accessed_object="none",
            status="blocked",
            elapsed_ms=_elapsed(t_start),
            row_count=0,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except AIServiceError as exc:
        logger.exception("[AI] LLM provider error for user=%s", current_user.email)
        _audit_ai(
            user=current_user,
            question=question,
            generated_sql="LLM_FAILURE",
            accessed_object="none",
            status="error",
            elapsed_ms=_elapsed(t_start),
            row_count=0,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is temporarily unavailable. Please try again later.",
        ) from exc

    # ── Step 4 + 5: Validate generated SQL through full 5-layer firewall ──────
    try:
        validate_query(raw_sql)
    except ValidationError as exc:
        reason = str(exc)
        logger.warning(
            "[AI] Generated SQL BLOCKED | user=%s reason=%s sql=%s",
            current_user.email,
            reason,
            raw_sql[:120],
        )
        _audit_ai(
            user=current_user,
            question=question,
            generated_sql=raw_sql,
            accessed_object=_infer_object(raw_sql),
            status="blocked",
            elapsed_ms=_elapsed(t_start),
            row_count=0,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"AI-generated SQL blocked by governance policy: {reason}",
        )

    # ── Step 6: Inject LIMIT if missing (mandatory role-based cap) ────────────
    final_sql = ai_orchestrator.inject_limit(raw_sql, current_user.role_name)
    accessed_object = _infer_object(final_sql)

    # ── Step 7: Audit BEFORE execution ────────────────────────────────────────
    _audit_ai(
        user=current_user,
        question=question,
        generated_sql=final_sql,
        accessed_object=accessed_object,
        status="success",
        elapsed_ms=None,   # timing not yet known
        row_count=None,
    )

    # ── Step 8: Execute in Databricks ─────────────────────────────────────────
    try:
        print("Executing final SQL:", final_sql)
        data = execute_query(final_sql)
    except Exception as exc:
        elapsed = _elapsed(t_start)
        logger.exception(
            "[AI] Execution failed | user=%s sql=%s", current_user.email, final_sql[:80]
        )
        _audit_ai(
            user=current_user,
            question=question,
            generated_sql=final_sql,
            accessed_object=accessed_object,
            status="error",
            elapsed_ms=elapsed,
            row_count=0,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Data retrieval failed. Please contact support.",
        ) from exc

    # ── Step 9: Post-execution audit with timing + row count ──────────────────
    elapsed_ms = _elapsed(t_start)
    _audit_ai(
        user=current_user,
        question=question,
        generated_sql=final_sql,
        accessed_object=accessed_object,
        status="success_completed",
        elapsed_ms=elapsed_ms,
        row_count=len(data),
    )

    # ── Step 10: Return response ───────────────────────────────────────────────
    return AskResponse(
        status="success",
        question=question,
        sql_generated=final_sql,
        rows_returned=len(data),
        data=data,
        accessed_object=accessed_object,
        execution_time_ms=round(elapsed_ms, 2),
        execution_timestamp=datetime.utcnow(),
    )


# ── Admin/introspection endpoint ──────────────────────────────────────────────

@router.get(
    "/ask/routes",
    summary="List Registered Intent Routes",
    description=(
        "Returns all predefined intent routes the AI can route questions to. "
        "Adding a new predefined report endpoint automatically appears here."
    ),
    tags=["AI Orchestration"],
)
def get_registered_routes() -> dict:
    """
    Returns the list of predefined routes the intent router knows about.
    Useful for understanding what questions the predefined-API path can handle.
    """
    routes = list_registered_routes()
    return {
        "registered_predefined_routes": routes,
        "count": len(routes),
        "description": (
            "Questions matching these routes are handled by predefined APIs "
            "(no LLM SQL generation). All other questions fall back to "
            "LLM-based SQL generation with 5-layer validation."
        ),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _elapsed(t_start: float) -> float:
    """Return wall-clock elapsed time in milliseconds since t_start."""
    return (time.perf_counter() - t_start) * 1000


def _infer_object(sql: str) -> str:
    """
    Best-effort extraction of the primary FROM clause object name for audit.
    Falls back gracefully — security is handled by the validator, not this fn.
    """
    import re
    match = re.search(r"\bFROM\s+([\w.]+)", sql, re.IGNORECASE)
    if match:
        parts = match.group(1).split(".")
        return parts[-1].lower()
    return "unknown"


def _audit_ai(
    *,
    user: UserContext,
    question: str,
    generated_sql: str,
    accessed_object: str,
    status: str,
    elapsed_ms: float | None,
    row_count: int | None,
) -> None:
    """Thin wrapper that calls the enhanced AI audit logger."""
    log_ai_event(
        user_email=user.email,
        role_name=user.role_name,
        question_text=question,
        generated_sql=generated_sql,
        accessed_object=accessed_object,
        execution_status=status,
        company_context=user.company_id,
        execution_time_ms=elapsed_ms,
        row_count=row_count,
    )
