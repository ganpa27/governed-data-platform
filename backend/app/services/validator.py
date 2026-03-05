"""
app/services/validator.py
─────────────────────────
SQL Governance Validator – Option B safety gate.

Implements a multi-layer defence:

  Layer 1 – Keyword blocklist  (fast regex pre-check)
  Layer 2 – AST parse via SQLGlot (syntax safety)
  Layer 3 – Statement-type whitelist (SELECT only)
  Layer 4 – Table/view allowlist (secure views only)
  Layer 5 – Disallowed-construct check (UNION, subquery on raw tables)

A query MUST pass ALL layers before it is allowed to execute.
If any layer raises ValidationError, the query is blocked and logged.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import sqlglot
import sqlglot.expressions as exp

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Constants ────────────────────────────────────────────────────────────────

# Regex blocklist – quick first-pass before we parse the AST.
# These patterns must NEVER appear anywhere in an allowed query.
_BLOCKED_KEYWORDS_PATTERN = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE"
    r"|GRANT|REVOKE|MERGE|REPLACE|CALL|LOAD|COPY|VACUUM|OPTIMIZE)\b",
    re.IGNORECASE,
)

# UNION is blocked because it can be used to side-channel data from
# tables that are not in the allowlist.
_BLOCKED_UNION_PATTERN = re.compile(r"\bUNION\b", re.IGNORECASE)

# Every allowed view – if a table reference is NOT in this set, block it.
_ALLOWED_VIEWS: frozenset[str] = frozenset(
    v.lower() for v in settings.allowed_views
)

# Raw / governance tables that must never be directly accessed.
_BLOCKED_TABLES = frozenset(
    [
        "revenue_transactions",
        "users",
        "audit_logs",
    ]
)


class ValidationError(Exception):
    """Raised when a query fails any validation layer."""


# ── Public API ────────────────────────────────────────────────────────────────

def validate_query(query: str) -> str:
    """
    Validate *query* through all safety layers.

    Returns the query string unchanged if valid.
    Raises ValidationError with a human-readable reason on failure.

    The caller is responsible for catching ValidationError and logging it
    as a 'blocked' audit event BEFORE returning a 403 to the client.
    """
    logger.info("Validating query: %s", query[:120])

    _layer1_keyword_blocklist(query)
    _layer2_union_block(query)
    ast = _layer3_parse(query)
    _layer4_statement_type(ast)
    _layer5_table_allowlist(ast)

    logger.info("Query passed all validation layers.")
    return query


# ── Validation layers (private) ───────────────────────────────────────────────

def _layer1_keyword_blocklist(query: str) -> None:
    """Layer 1: Regex keyword blocklist."""
    match = _BLOCKED_KEYWORDS_PATTERN.search(query)
    if match:
        keyword = match.group(0).upper()
        raise ValidationError(
            f"Blocked keyword detected: '{keyword}'. "
            "Only SELECT statements are permitted."
        )


def _layer2_union_block(query: str) -> None:
    """Layer 2: UNION is blocked – it can bypass view-level restrictions."""
    if _BLOCKED_UNION_PATTERN.search(query):
        raise ValidationError(
            "UNION operations are not permitted. "
            "Query only a single secure view per request."
        )


def _layer3_parse(query: str) -> exp.Expression:
    """Layer 3: Parse the query with SQLGlot. Raises on syntax errors."""
    try:
        statements = sqlglot.parse(query, dialect="spark")
    except Exception as exc:
        raise ValidationError(f"SQL syntax error: {exc}") from exc

    if not statements or len(statements) != 1 or statements[0] is None:
        raise ValidationError(
            "Exactly one SQL statement is required per request."
        )

    return statements[0]


def _layer4_statement_type(ast: exp.Expression) -> None:
    """Layer 4: Only SELECT statements are allowed."""
    if not isinstance(ast, exp.Select):
        stmt_type = type(ast).__name__.upper()
        raise ValidationError(
            f"Statement type '{stmt_type}' is not permitted. "
            "Only SELECT is allowed."
        )


def _layer5_table_allowlist(ast: exp.Expression) -> None:
    """
    Layer 5: All table/view references must be in the allowlist.

    We walk the AST and extract every Table node.
    Any reference to a raw or governance table is blocked.
    Any reference to a view NOT in the allowlist is blocked.
    """
    referenced_tables: list[str] = []

    for table_node in ast.find_all(exp.Table):
        # SQLGlot stores table name in .name, schema in .db, catalog in .catalog
        name: Optional[str] = table_node.name
        if name:
            referenced_tables.append(name.lower())

    if not referenced_tables:
        raise ValidationError("No table or view reference found in query.")

    for table_name in referenced_tables:
        if table_name in _BLOCKED_TABLES:
            raise ValidationError(
                f"Direct access to '{table_name}' is not permitted. "
                "Use the secure governed views instead."
            )
        if table_name not in _ALLOWED_VIEWS:
            raise ValidationError(
                f"Table or view '{table_name}' is not in the permitted view list. "
                f"Allowed views: {sorted(_ALLOWED_VIEWS)}."
            )
