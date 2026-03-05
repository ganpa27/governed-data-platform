"""
app/models/schemas.py
─────────────────────
Shared Pydantic v2 request / response / internal models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ── Identity ─────────────────────────────────────────────────────────────────

class UserContext(BaseModel):
    """Resolved identity of the authenticated caller."""
    user_id: str
    email: str
    role_name: str  # admin | finance_user | auditor
    company_id: Optional[str] = None  # None for admin


# ── API request models ────────────────────────────────────────────────────────

class FreeSQLRequest(BaseModel):
    """Payload for POST /execute-query (Option B)."""
    query: str = Field(
        ...,
        min_length=6,
        max_length=4096,
        examples=["SELECT * FROM secure_revenue_quarterly LIMIT 10"],
        description="A SELECT-only SQL query targeting secure views.",
    )

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()


class AskRequest(BaseModel):
    """Payload for POST /ask (Stage 3 – AI orchestration)."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=1024,
        examples=["Show quarterly revenue for my company"],
        description="A natural language question about governed financial data.",
    )

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        return v.strip()


# ── API response models ───────────────────────────────────────────────────────

class QueryResponse(BaseModel):
    """Unified response envelope for all query endpoints."""
    status: str = "success"
    rows_returned: int
    data: list[dict[str, Any]]
    accessed_object: str
    execution_timestamp: datetime = Field(default_factory=datetime.utcnow)


class AskResponse(BaseModel):
    """Response envelope for POST /ask (AI orchestration)."""
    status: str = "success"
    question: str
    sql_generated: str
    rows_returned: int
    data: list[dict[str, Any]]
    accessed_object: str
    execution_time_ms: float
    execution_timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    status: str
    environment: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditEntry(BaseModel):
    """Internal model representing a single audit log record."""
    user_email: str
    role_name: str
    query_type: str        # predefined | free_sql | ai_query
    query_text: str
    accessed_object: str   # view name
    execution_status: str  # success | blocked | error
    company_context: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # ── AI-specific fields (Stage 3) – optional for backward compat ──────────
    question_text: Optional[str] = None    # original NL question
    generated_sql: Optional[str] = None   # SQL produced by LLM
    execution_time_ms: Optional[float] = None
    row_count: Optional[int] = None
