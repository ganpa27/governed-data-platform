"""
app/api/predefined.py
─────────────────────
Option A – Predefined Reports (Most Secure Execution Model)

Design principles:
  - Zero raw SQL from callers.
  - All queries are hardcoded constants inside this module.
  - Every request is authenticated + audited.
  - Results always come from the secure governed views.

Endpoints:
  GET /reports/yearly-revenue
  GET /reports/quarterly-revenue
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import execute_query
from app.core.security import get_current_user
from app.core.config import get_settings
from app.models.schemas import QueryResponse, UserContext
from app.services.audit import log_event

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/reports", tags=["Predefined Reports"])

# ── Hardcoded governed queries ────────────────────────────────────────────────
# These strings NEVER change at runtime – zero injection surface.

_YEARLY_VIEW = "secure_revenue_yearly"
_QUARTERLY_VIEW = "secure_revenue_quarterly"

_SQL_YEARLY = (
    f"SELECT * FROM {settings.databricks_catalog}"
    f".{settings.databricks_schema}.{_YEARLY_VIEW}"
)

_SQL_QUARTERLY = (
    f"SELECT * FROM {settings.databricks_catalog}"
    f".{settings.databricks_schema}.{_QUARTERLY_VIEW}"
)


# ── Route: GET /reports/yearly-revenue ───────────────────────────────────────

@router.get(
    "/yearly-revenue",
    response_model=QueryResponse,
    summary="Annual Revenue Report",
    description=(
        "Returns aggregated yearly revenue, cost, and profit per company. "
        "Security is enforced by the `secure_revenue_yearly` view "
        "(row-filtering + profit masking based on caller's role)."
    ),
)
def get_yearly_revenue(
    current_user: Annotated[UserContext, Depends(get_current_user)],
    limit: Optional[int] = Query(
        default=None, ge=1, le=10_000, description="Optional row limit."
    ),
) -> QueryResponse:
    sql = _SQL_YEARLY
    if limit:
        sql = f"{sql} LIMIT {limit}"

    _execute_report(
        user=current_user,
        sql=sql,
        accessed_object=_YEARLY_VIEW,
    )

    return _run_report(
        user=current_user,
        sql=sql,
        accessed_object=_YEARLY_VIEW,
    )


# ── Route: GET /reports/quarterly-revenue ────────────────────────────────────

@router.get(
    "/quarterly-revenue",
    response_model=QueryResponse,
    summary="Quarterly Revenue Report",
    description=(
        "Returns aggregated quarterly revenue, cost, and profit per company. "
        "Security is enforced by the `secure_revenue_quarterly` view."
    ),
)
def get_quarterly_revenue(
    current_user: Annotated[UserContext, Depends(get_current_user)],
    limit: Optional[int] = Query(
        default=None, ge=1, le=10_000, description="Optional row limit."
    ),
) -> QueryResponse:
    sql = _SQL_QUARTERLY
    if limit:
        sql = f"{sql} LIMIT {limit}"

    return _run_report(
        user=current_user,
        sql=sql,
        accessed_object=_QUARTERLY_VIEW,
    )


# ── Shared execution helper ───────────────────────────────────────────────────

def _run_report(
    *,
    user: UserContext,
    sql: str,
    accessed_object: str,
) -> QueryResponse:
    """
    Log → Execute → Return.
    Audit entry is written BEFORE execution per governance rules.
    """
    # ── Audit BEFORE execution ───────────────────────────────────────────────
    log_event(
        user_email=user.email,
        role_name=user.role_name,
        query_type="predefined",
        query_text=sql,
        accessed_object=accessed_object,
        execution_status="success",   # optimistic; updated on error below
        company_context=user.company_id,
    )

    # ── Execute ──────────────────────────────────────────────────────────────
    try:
        data = execute_query(sql)
    except Exception as exc:
        logger.exception("Predefined report execution failed: %s", accessed_object)
        # Emit an error audit event (best-effort – log_event never raises).
        log_event(
            user_email=user.email,
            role_name=user.role_name,
            query_type="predefined",
            query_text=sql,
            accessed_object=accessed_object,
            execution_status="error",
            company_context=user.company_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve report from Databricks.",
        ) from exc

    return QueryResponse(
        status="success",
        rows_returned=len(data),
        data=data,
        accessed_object=accessed_object,
        execution_timestamp=datetime.utcnow(),
    )


# Alias to avoid lint warning on unused import in the first route handler.
_execute_report = _run_report
