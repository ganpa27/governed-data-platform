"""
app/services/audit.py
─────────────────────
Audit Logging Service.

Architecture decision: audit logging is a TWO-LAYER mechanism:

  Layer A – Application-level logging (Python logging → file / stdout)
            Always present; survives even if the DB is unavailable.

  Layer B – Database-level logging (writes to governance_schema.audit_logs)
            Best-effort; a failure must NEVER prevent query execution.

This ensures governance audit trail can't be silently lost because of a
transient DB write error, while still maintaining the Databricks audit table
that the blueprint requires.

CRITICAL: log_event() and log_ai_event() must be called BEFORE query execution
          so that even queries that crash mid-execution are recorded.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
from app.core.database import execute_query
from app.models.schemas import AuditEntry

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Stage 2: Standard audit event ────────────────────────────────────────────

def log_event(
    *,
    user_email: str,
    role_name: str,
    query_type: str,
    query_text: str,
    accessed_object: str,
    execution_status: str,
    company_context: Optional[str] = None,
) -> None:
    """
    Record an audit event in both application logs and the Databricks audit table.

    Args:
        user_email: Authenticated caller's email.
        role_name: Caller's resolved role (admin | finance_user | auditor).
        query_type: 'predefined' or 'free_sql'.
        query_text: The exact SQL (or report name) being executed.
        accessed_object: The primary view / object being accessed.
        execution_status: 'success' | 'blocked' | 'error'.
        company_context: company_id filter in effect, if applicable.

    Note: This function intentionally never raises.  A logging failure must
          not abort the calling request.
    """
    entry = AuditEntry(
        user_email=user_email,
        role_name=role_name,
        query_type=query_type,
        query_text=query_text[:2000],   # truncate for DB column safety
        accessed_object=accessed_object,
        execution_status=execution_status,
        company_context=company_context,
        timestamp=datetime.utcnow(),
    )

    # ── Layer A: Application log (always) ────────────────────────────────────
    _log_to_application(entry)

    # ── Layer B: Database log (best-effort) ──────────────────────────────────
    _log_to_database(entry)


# ── Stage 3: Enhanced AI audit event ─────────────────────────────────────────

def log_ai_event(
    *,
    user_email: str,
    role_name: str,
    question_text: str,
    generated_sql: str,
    accessed_object: str,
    execution_status: str,
    company_context: Optional[str] = None,
    execution_time_ms: Optional[float] = None,
    row_count: Optional[int] = None,
) -> None:
    """
    Enhanced audit logger for Stage 3 AI-orchestrated queries.

    Captures everything log_event() does PLUS:
      - question_text:     the original natural language question
      - generated_sql:     the SQL produced by the LLM (may be BLOCKED)
      - execution_time_ms: end-to-end latency
      - row_count:         number of rows returned (or 0 if blocked/error)

    Called twice per AI request:
      1. BEFORE execution (status='success',           timing=None)
      2. AFTER  execution (status='success_completed', timing=<ms>)

    Like log_event(), this function intentionally never raises.
    """
    entry = AuditEntry(
        user_email=user_email,
        role_name=role_name,
        query_type="ai_query",
        query_text=generated_sql[:2000],
        accessed_object=accessed_object,
        execution_status=execution_status,
        company_context=company_context,
        timestamp=datetime.utcnow(),
        # AI-specific fields
        question_text=question_text[:1000],
        generated_sql=generated_sql[:2000],
        execution_time_ms=execution_time_ms,
        row_count=row_count,
    )

    # ── Layer A: Application log (always) ────────────────────────────────────
    _log_ai_to_application(entry)

    # ── Layer B: Database log (best-effort) ──────────────────────────────────
    # Note: AI fields (question_text, generated_sql, etc.) require the
    # audit_logs table to have the corresponding extra columns.
    # If they don't exist yet, the INSERT silently degrades (Layer B never raises).
    _log_to_database(entry)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _log_to_application(entry: AuditEntry) -> None:
    """Write a structured audit line to the application logger."""
    logger.info(
        "[AUDIT] user=%s role=%s type=%s object=%s status=%s company=%s | %s",
        entry.user_email,
        entry.role_name,
        entry.query_type,
        entry.accessed_object,
        entry.execution_status,
        entry.company_context or "ALL",
        entry.query_text[:80],
    )


def _log_ai_to_application(entry: AuditEntry) -> None:
    """Write a structured AI audit line with extra fields to the application logger."""
    logger.info(
        "[AUDIT][AI] user=%s role=%s status=%s object=%s ms=%s rows=%s | "
        "question='%s' | sql='%s'",
        entry.user_email,
        entry.role_name,
        entry.execution_status,
        entry.accessed_object,
        f"{entry.execution_time_ms:.1f}" if entry.execution_time_ms is not None else "N/A",
        entry.row_count if entry.row_count is not None else "N/A",
        (entry.question_text or "")[:80],
        (entry.generated_sql or "")[:80],
    )


def _log_to_database(entry: AuditEntry) -> None:
    """
    Insert one row into governance_schema.audit_logs.
    Silently catches and logs any exception so callers are never disrupted.
    """
    def esc(s: str) -> str:
        """Escape single quotes to prevent injection into the audit INSERT."""
        return s.replace("'", "''") if s else ""

    sql = f"""
        INSERT INTO {settings.databricks_catalog}.{settings.databricks_governance_schema}.audit_logs
        (user_email, role_name, query_type, accessed_object, access_timestamp, company_context)
        VALUES (
            '{esc(entry.user_email)}',
            '{esc(entry.role_name)}',
            '{esc(entry.query_type)}',
            '{esc(entry.accessed_object)}',
            '{entry.timestamp.isoformat()}',
            '{esc(entry.company_context or "ALL")}'
        )
    """
    try:
        execute_query(sql)
        logger.debug("Audit entry persisted to Databricks.")
    except Exception as exc:
        # Layer B failure must NOT propagate.
        logger.error(
            "Failed to persist audit entry to Databricks (continuing): %s", exc
        )
