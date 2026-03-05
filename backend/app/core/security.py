"""
app/core/security.py
────────────────────
Authentication helpers.

Current implementation: simple API-key / Bearer-token stub that reads the
calling user's email + role from the Databricks governance_schema.users table.

Future: swap verify_token() for a full OAuth 2.0 / OIDC flow.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.database import get_connection
from app.models.schemas import UserContext

logger = logging.getLogger(__name__)
settings = get_settings()

_bearer_scheme = HTTPBearer(auto_error=True)


def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer_scheme)],
) -> UserContext:
    """
    Validate the Bearer token and return the resolved UserContext.

    For now the "token" IS the user's email (plain-text demo mode).
    In production this will be a signed JWT; the sub claim will carry the email.

    Security note: this function intentionally fails loudly – any ambiguity
    about identity must raise an authentication error, never silently pass.
    """
    token: str = credentials.credentials.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
        )

    # ── Resolve user from governance table ──────────────────────────────────
    user_email = _resolve_email_from_token(token)
    user_ctx = _load_user_context(user_email)
    return user_ctx


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────

def _resolve_email_from_token(token: str) -> str:
    """
    Token → email mapping.

    Demo mode: token IS the email.
    Production: decode JWT, extract sub claim.
    """
    # TODO: replace with JWT decode when OAuth2 is wired up
    return token


def _load_user_context(email: str) -> UserContext:
    """
    Query governance_schema.users to get role + company_id for this email.
    Raises 401 if the user is not registered.
    """
    sql = f"""
        SELECT user_id, email, role_name, company_id
        FROM {settings.databricks_catalog}.{settings.databricks_governance_schema}.users
        WHERE email = '{email}'
        LIMIT 1
    """

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
    except Exception as exc:
        logger.exception("Failed to query governance users table.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify identity at this time.",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found in governance registry.",
        )

    user_id, db_email, role_name, company_id = row
    return UserContext(
        user_id=str(user_id),
        email=db_email,
        role_name=role_name,
        company_id=str(company_id) if company_id is not None else None,
    )


# ── Dependency aliases ───────────────────────────────────────────────────────

def get_current_user(
    user: Annotated[UserContext, Depends(verify_token)],
) -> UserContext:
    return user
