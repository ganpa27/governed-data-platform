"""
app/api/free_sql.py
───────────────────
Option B – Controlled Free SQL Engine (Power Mode)

Execution pipeline (per blueprint):
  1. Decode user session            → get_current_user()
  2. Validate SQL using SQLGlot     → validator.validate_query()
  3. Allow SELECT only              │  (enforced inside validator)
  4. Restrict to secure views        │
  5. Log audit entry                → audit.log_event()   ← BEFORE execution
  6. Execute in Databricks          → database.execute_query()
  7. Return results

Blocked: DROP, DELETE, UPDATE, INSERT, ALTER, CREATE, UNION,
         raw tables, governance tables.

Allowed: SELECT, WHERE, GROUP BY, ORDER BY, LIMIT.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import execute_query
from app.core.security import get_current_user
from app.core.config import get_settings
from app.models.schemas import FreeSQLRequest, QueryResponse, UserContext
from app.services.audit import log_event
from app.services.validator import ValidationError, validate_query

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["Controlled SQL Engine"])


@router.post(
    "/execute-query",
    response_model=QueryResponse,
    summary="Execute a Controlled SELECT Query",
    description=(
        "Power-mode endpoint: submit a SELECT-only query against the "
        "permitted secure views. The query is validated through 5 layers "
        "before execution. Non-SELECT statements and raw-table references "
        "are blocked and audit-logged."
    ),
    responses={
        400: {"description": "Malformed request body."},
        403: {"description": "Query blocked by governance validator."},
        422: {"description": "Request validation error."},
        502: {"description": "Databricks execution failure."},
    },
)
def execute_free_sql(
    payload: FreeSQLRequest,
    current_user: Annotated[UserContext, Depends(get_current_user)],
) -> QueryResponse:
    """
    Controlled SQL execution endpoint.

    Security note: the user-supplied query is NEVER concatenated into
    any string that reaches the database without first passing
    all five validator layers.
    """
    query = payload.query

    # ── Infer the primary accessed object for audit purposes ─────────────────
    accessed_object = _infer_accessed_object(query)

    # ── Step 2-4: Validate (blocks on any policy violation) ──────────────────
    try:
        validate_query(query)
    except ValidationError as exc:
        reason = str(exc)
        logger.warning(
            "Query BLOCKED for user=%s reason=%s query=%s",
            current_user.email,
            reason,
            query[:120],
        )
        # ── Step 5: Audit BLOCKED event before returning 403 ─────────────────
        log_event(
            user_email=current_user.email,
            role_name=current_user.role_name,
            query_type="free_sql",
            query_text=query,
            accessed_object=accessed_object,
            execution_status="blocked",
            company_context=current_user.company_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Query blocked by governance policy: {reason}",
        )

    # ── Step 5: Audit SUCCESS event BEFORE execution ──────────────────────────
    log_event(
        user_email=current_user.email,
        role_name=current_user.role_name,
        query_type="free_sql",
        query_text=query,
        accessed_object=accessed_object,
        execution_status="success",
        company_context=current_user.company_id,
    )

    # ── Step 6: Execute in Databricks ────────────────────────────────────────
    try:
        data = execute_query(query)
    except Exception as exc:
        logger.exception(
            "Free-SQL execution failed for user=%s", current_user.email
        )
        log_event(
            user_email=current_user.email,
            role_name=current_user.role_name,
            query_type="free_sql",
            query_text=query,
            accessed_object=accessed_object,
            execution_status="error",
            company_context=current_user.company_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Databricks execution failed. Check server logs.",
        ) from exc

    # ── Step 7: Return results ────────────────────────────────────────────────
    return QueryResponse(
        status="success",
        rows_returned=len(data),
        data=data,
        accessed_object=accessed_object,
        execution_timestamp=datetime.utcnow(),
    )


# ── Helper ────────────────────────────────────────────────────────────────────

def _infer_accessed_object(query: str) -> str:
    """
    Best-effort extraction of the primary FROM table/view name for audit.
    Falls back to 'unknown' – this is cosmetic; security is handled by the
    validator's allowlist, not this function.
    """
    import re
    match = re.search(r"\bFROM\s+([\w.]+)", query, re.IGNORECASE)
    if match:
        # Strip catalog/schema prefix if present, keep only the view name.
        parts = match.group(1).split(".")
        return parts[-1].lower()
    return "unknown"
