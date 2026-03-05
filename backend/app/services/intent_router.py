"""
app/services/intent_router.py
─────────────────────────────
Intent Router – Stage 3 Enhancement

PURPOSE:
  When a user asks a natural language question via POST /ask, instead of
  immediately asking the LLM to generate raw SQL, we FIRST attempt to
  match the question's intent to an existing predefined API endpoint.

  Only if no predefined route matches do we fall back to LLM-based SQL
  generation (the current flow in ai_orchestrator.py).

WHY THIS MAKES THE SYSTEM EXPANDABLE:
  - Adding a new predefined report  → automatically extends what AI can answer
  - No new LLM logic needed         → just register a new IntentRoute below
  - Predefined routes are 100% safe → no raw SQL, no hallucination risk
  - Falls back gracefully           → unknown questions still go to LLM path

ROUTING STRATEGY:
  1. Keyword/phrase matching (fast, deterministic, zero API cost)
  2. LLM-based intent classification (if keyword match is ambiguous)  [future]
  3. Fallback → ai_orchestrator.generate_sql()

PREDEFINED ROUTES REGISTERED:
  "yearly revenue"    → GET /reports/yearly-revenue   (secure_revenue_yearly)
  "quarterly revenue" → GET /reports/quarterly-revenue (secure_revenue_quarterly)
  (Add more here as new predefined report endpoints are created)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.core.database import execute_query
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Intent Route Definition ───────────────────────────────────────────────────

@dataclass
class IntentRoute:
    """
    Represents a mapping from a natural language intent to a predefined query.

    Fields:
      name         – Human-readable name for logging/audit.
      keywords     – If ANY of these appear in the question, this route matches.
      phrases      – Multi-word phrases that must appear as-is (stronger signal).
      view_name    – The secure governed view to query.
      sql_builder  – A callable that returns the full SQL string to execute.
                     Receives (catalog, schema, limit) as arguments.
    """
    name: str
    keywords: list[str]
    phrases: list[str]
    view_name: str
    sql_builder: Callable[[str, str, int], str]
    # If True, this route requires an EXACT phrase match (avoids false positives)
    require_phrase: bool = False

    def matches(self, question: str) -> bool:
        """
        Return True if this route's keywords/phrases match the normalized question.

        Matching logic:
          - If require_phrase=True  → at least one phrase must match
          - If require_phrase=False → at least one keyword OR phrase must match
        """
        q = question.lower()

        # Check phrase matches
        for phrase in self.phrases:
            if phrase.lower() in q:
                logger.debug("[IntentRouter] Phrase match: '%s' → route '%s'", phrase, self.name)
                return True

        if self.require_phrase:
            return False  # phrases required, none matched

        # Check keyword matches
        for kw in self.keywords:
            # Use word-boundary match to avoid partial matches (e.g. "year" in "player")
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', q):
                logger.debug("[IntentRouter] Keyword match: '%s' → route '%s'", kw, self.name)
                return True

        return False


# ── SQL Builder Helpers ───────────────────────────────────────────────────────

def _build_yearly_sql(catalog: str, schema: str, limit: int) -> str:
    return (
        f"SELECT * FROM {catalog}.{schema}.secure_revenue_yearly"
        f" LIMIT {limit}"
    )


def _build_quarterly_sql(catalog: str, schema: str, limit: int) -> str:
    return (
        f"SELECT * FROM {catalog}.{schema}.secure_revenue_quarterly"
        f" LIMIT {limit}"
    )


# ── Route Registry ────────────────────────────────────────────────────────────
#
# ORDER MATTERS: Routes are evaluated top-to-bottom.
# More specific routes (quarterly) should come BEFORE general ones (yearly).
#
# TO ADD A NEW REPORT: append a new IntentRoute here.
# The system will automatically consider it when routing /ask questions.

_ROUTES: list[IntentRoute] = [
    IntentRoute(
        name="quarterly_revenue",
        keywords=["quarter", "quarterly", "q1", "q2", "q3", "q4"],
        phrases=["quarterly revenue", "by quarter", "each quarter", "per quarter"],
        view_name="secure_revenue_quarterly",
        sql_builder=_build_quarterly_sql,
    ),
    IntentRoute(
        name="yearly_revenue",
        keywords=["year", "yearly", "annual", "annually", "2023", "2024", "2025"],
        phrases=["yearly revenue", "annual revenue", "by year", "each year", "per year"],
        view_name="secure_revenue_yearly",
        sql_builder=_build_yearly_sql,
    ),
]


# ── Public API ────────────────────────────────────────────────────────────────

@dataclass
class RouteResult:
    """
    Result returned from route_question().

    matched:       True if a predefined route was found.
    route_name:    Name of the matched route (or None).
    view_name:     The secure governed view that was queried (or None).
    sql_executed:  The exact SQL string that was executed (or None).
    data:          The query results (list of dicts).
    """
    matched: bool
    route_name: Optional[str] = None
    view_name: Optional[str] = None
    sql_executed: Optional[str] = None
    data: list[dict[str, Any]] = field(default_factory=list)


def route_question(question: str, user_role: str) -> RouteResult:
    """
    Attempt to route a natural language question to a predefined API.

    Algorithm:
      1. Normalize the question.
      2. Iterate over _ROUTES in order; return on first match.
      3. For matched route, build the SQL and execute it.
      4. Return RouteResult(matched=True, ...) on success.
      5. Return RouteResult(matched=False) if no route matched → caller
         should fall back to LLM SQL generation.

    Args:
        question:  Natural language question from the user.
        user_role: The caller's role name (used for row limit lookup).

    Returns:
        RouteResult with matched=True and populated data if routed,
        OR RouteResult(matched=False) to signal fallback to LLM path.
    """
    logger.info("[IntentRouter] Routing question: '%s' (role=%s)", question[:80], user_role)

    for route in _ROUTES:
        if route.matches(question):
            logger.info(
                "[IntentRouter] Matched route '%s' → view '%s'",
                route.name,
                route.view_name,
            )

            # Get role-based row limit
            limit = settings.role_row_limits.get(user_role, settings.default_row_limit)

            # Build the predefined SQL (catalog-qualified, role-limited)
            sql = route.sql_builder(
                settings.databricks_catalog,
                settings.databricks_schema,
                limit,
            )

            logger.info("[IntentRouter] Executing predefined SQL: %s", sql)

            # Execute using the same secure execution layer as predefined reports
            data = execute_query(sql)

            return RouteResult(
                matched=True,
                route_name=route.name,
                view_name=route.view_name,
                sql_executed=sql,
                data=data,
            )

    # No predefined route matched → signal LLM fallback
    logger.info(
        "[IntentRouter] No predefined route matched for question: '%s' → falling back to LLM",
        question[:80],
    )
    return RouteResult(matched=False)


def list_registered_routes() -> list[dict[str, Any]]:
    """
    Return a summary of all registered intent routes.
    Useful for /docs, health-checks, or admin introspection endpoints.
    """
    return [
        {
            "name": r.name,
            "view": r.view_name,
            "sample_keywords": r.keywords[:4],
            "sample_phrases": r.phrases[:2],
        }
        for r in _ROUTES
    ]
