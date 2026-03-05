"""
app/services/ai_orchestrator.py
────────────────────────────────
Stage 3 – AI Orchestration Service.

Responsibility (STRICTLY LIMITED):
  - Receive a natural language question
  - Call the configured LLM provider
  - Return the raw SQL string

This service does NOT:
  - Validate the SQL (that is validator.py's job)
  - Execute the SQL (that is database.py's job)
  - Make any trust decision (the validator is the gatekeeper)

Security principle:
  AI output is UNTRUSTED.
  Every string returned here MUST pass through validate_query() before
  it can ever reach the database.

LLM Providers:
    mock   – Returns safe, hardcoded SQL. Use in development / CI.
    openai – Calls OpenAI Chat Completions API (gpt-4o-mini by default).
    groq   – Calls Groq API (fast inference) via OpenAI compatibility layer.
    kimi   – (Commented out / Legacy) Calls Kimi (Moonshot AI) API. 
    azure  – Stub placeholder for Azure OpenAI (not yet implemented).

  Configuration (via .env):
    LLM_PROVIDER=openai | groq | mock | azure | kimi

  # OpenAI
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL=gpt-4o-mini

  # Groq (Current default AI)
  GROQ_API_KEY=gsk-...
  GROQ_MODEL=llama3-70b-8192
  GROQ_BASE_URL=https://api.groq.com/openai/v1

  # Kimi (Legacy)
  # KIMI_API_KEY=sk-...
  # KIMI_MODEL=moonshot-v1-8k
  # KIMI_BASE_URL=https://api.moonshot.cn/v1

  # Shared
  AI_MAX_TOKENS=500
  AI_TEMPERATURE=0.1
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── System prompt ─────────────────────────────────────────────────────────────
# This is the single most important security control on the AI side.
# The prompt is explicit about allowed tables, statement types, and output format.
# Remember: the validator is the real gatekeeper – this prompt is defence-in-depth.

_SYSTEM_PROMPT = """You are a SQL generation assistant for a governed financial data platform.

STRICT RULES – you MUST follow these without exception:
1. Generate ONLY a single SELECT statement.
2. You may ONLY query these two views:
     - secure_revenue_yearly
     - secure_revenue_quarterly
3. Do NOT use any other table, view, or schema.
4. Do NOT use UNION, JOIN, subqueries, CTEs, or window functions.
5. Do NOT use DROP, DELETE, UPDATE, INSERT, ALTER, CREATE, or any DDL/DML.
6. Do NOT access governance_schema, revenue_transactions, users, or audit_logs.
7. Output ONLY the raw SQL query — no explanation, no markdown, no code fences.
8. If the question cannot be answered with the two allowed views, output exactly:
   CANNOT_ANSWER

CRITICAL VALUE RULE:
9. NEVER use placeholders, variables, or bind parameters such as :company_id,
   %(name)s, ?, $1, <value>, or ANY symbolic substitution.
   You MUST embed the EXACT literal value extracted from the user's question
   directly into the SQL.
   WRONG:  WHERE company_id = :company_id
   CORRECT: WHERE company_id = 'C001'
   If the user's question contains a company ID, year, quarter, or number,
   put that exact value as a quoted string or integer literal in the SQL.
   If you cannot determine the literal value from the question, output CANNOT_ANSWER.

Available columns in secure_revenue_yearly:
  company_id (string), year (int), total_revenue (double),
  total_cost (double), total_profit (double)

Available columns in secure_revenue_quarterly:
  company_id (string), year (int), quarter (string e.g. 'Q1'),
  total_revenue (double), total_cost (double), total_profit (double)

Security note: this output will be validated by a strict SQL firewall before execution.
"""

# ── Public API ────────────────────────────────────────────────────────────────

class AIServiceError(Exception):
    """Raised when the LLM provider fails or is unavailable."""


def generate_sql(question: str, user_role: str) -> str:
    """
    Translate a natural language *question* into a SQL string.

    Args:
        question:  The user's NL question (already sanitised by Pydantic).
        user_role: The caller's role — used to build a role-aware user prompt.

    Returns:
        A raw SQL string (NOT yet validated or executed).

    Raises:
        AIServiceError: If the LLM call fails (→ caller returns HTTP 503).
        ValueError:     If the LLM returns CANNOT_ANSWER (→ caller returns 400).
    """
    provider = settings.llm_provider.lower()
    logger.info(
        "[AI] Generating SQL | provider=%s role=%s question=%s",
        provider,
        user_role,
        question[:80],
    )

    if provider == "mock":
        sql = _mock_provider(question)
    elif provider == "openai":
        sql = _openai_provider(question, user_role)
    elif provider == "groq":
        sql = _groq_provider(question, user_role)
    elif provider == "kimi":
        sql = _kimi_provider(question, user_role)
    elif provider == "azure":
        raise AIServiceError(
            "Azure OpenAI provider is not yet implemented. "
            "Set LLM_PROVIDER=mock, LLM_PROVIDER=groq, or LLM_PROVIDER=openai."
        )
    else:
        raise AIServiceError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Valid options: mock | openai | groq | azure | kimi."
        )

    # Validate the LLM's meta-response before returning
    sql = _clean_llm_output(sql)

    if sql.upper() == "CANNOT_ANSWER":
        raise ValueError(
            "The AI cannot answer this question using the available governed views. "
            "Please ask about yearly or quarterly revenue data."
        )

    # Guard: reject queries that still contain bind-parameter placeholders.
    # e.g. :company_id, %(name)s, ?, $1  — these cannot be executed by Databricks
    # and indicate the LLM failed to embed a literal value from the question.
    _check_no_placeholders(sql)

    logger.info("[AI] Raw SQL from LLM: %s", sql[:120])
    return sql


def inject_limit(sql: str, role: str) -> str:
    """
    Ensure the query has a LIMIT clause.

    If the AI-generated SQL already contains LIMIT, leave it unchanged.
    Otherwise, append LIMIT <role_cap> to prevent bulk data exfiltration.

    This is a mandatory safeguard — it runs AFTER validation (since
    the validator checks the original SQL) but BEFORE execution.
    The LIMIT is role-aware: admins get a higher cap than auditors.

    Args:
        sql:  Validated SQL string.
        role: The caller's role_name.

    Returns:
        SQL string guaranteed to contain a LIMIT clause.
    """
    if re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        logger.debug("[AI] Query already has LIMIT — not injecting.")
        return sql

    cap = settings.role_row_limits.get(role, settings.default_row_limit)
    injected = f"{sql.rstrip().rstrip(';')} LIMIT {cap}"
    logger.info("[AI] Injected LIMIT %d for role=%s", cap, role)
    return injected


# ── LLM Provider implementations ──────────────────────────────────────────────

def _mock_provider(question: str) -> str:
    """
    Mock LLM provider for development / CI.

    Returns safe hardcoded SQL that ALWAYS passes validation.
    Simulates a small processing delay for realism.

    For questions mentioning known bad intent (DROP, users, transactions),
    returns CANNOT_ANSWER so the error path is exercised in tests.
    """
    time.sleep(0.05)  # simulate LLM latency

    q = question.lower()

    # Simulate the LLM correctly refusing hostile prompts
    _hostile_terms = [
        "drop", "delete", "truncate", "insert", "update",
        "revenue_transactions", "governance", "users table",
        "audit_log", "union",
    ]
    if any(term in q for term in _hostile_terms):
        return "CANNOT_ANSWER"

    # Route to the most appropriate view based on the question's keywords
    if any(word in q for word in ["quarter", "q1", "q2", "q3", "q4", "quarterly"]):
        return "SELECT * FROM secure_revenue_quarterly"
    elif any(word in q for word in ["year", "annual", "yearly", "2023", "2024"]):
        return "SELECT * FROM secure_revenue_yearly"
    else:
        # Default: quarterly view is the richer dataset
        return "SELECT * FROM secure_revenue_quarterly"


def _openai_provider(question: str, user_role: str) -> str:
    """
    Real OpenAI Chat Completions provider.

    Uses a role-aware user prompt so the LLM understands the
    permission context without having direct access to it.

    Raises:
        AIServiceError: On any API or network failure.
    """
    if not settings.openai_api_key:
        raise AIServiceError(
            "OPENAI_API_KEY is not set. "
            "Either set LLM_PROVIDER=mock or provide a valid API key."
        )

    try:
        from openai import OpenAI  # lazy import – avoids import error in mock mode
    except ImportError as exc:
        raise AIServiceError(
            "openai package is not installed. Run: pip install openai"
        ) from exc

    user_prompt = (
        f"Role context: you are a {user_role} in the platform. "
        f"Question: {question}"
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )
    except Exception as exc:
        logger.exception("[AI] OpenAI API call failed.")
        raise AIServiceError(f"LLM provider error: {exc}") from exc

    raw: Optional[str] = response.choices[0].message.content
    if not raw:
        raise AIServiceError("LLM returned an empty response.")

    return raw.strip()


def _kimi_provider(question: str, user_role: str) -> str:
    """
    Kimi (Moonshot AI) Chat Completions provider.
    (Currently legacy/fallback, we are using Groq primarily)

    Kimi's API is fully OpenAI-compatible: same SDK, same request/response
    format — only base_url and api_key differ.

    Available models:
      moonshot-v1-8k    – fast, good for short SQL generation tasks
      moonshot-v1-32k   – larger context window
      moonshot-v1-128k  – maximum context (not needed for SQL gen)

    API docs: https://platform.moonshot.cn/docs

    Raises:
        AIServiceError: On any API or network failure.
    """
    if not settings.kimi_api_key:
        raise AIServiceError(
            "KIMI_API_KEY is not set. "
            "Add it to your .env file or set LLM_PROVIDER=mock."
        )

    try:
        from openai import OpenAI  # lazy import – same client, different base_url
    except ImportError as exc:
        raise AIServiceError(
            "openai package is not installed. Run: pip install openai"
        ) from exc

    user_prompt = (
        f"Role context: you are a {user_role} in the platform. "
        f"Question: {question}"
    )

    try:
        # Point the OpenAI client at Kimi's endpoint
        client = OpenAI(
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
        )
        response = client.chat.completions.create(
            model=settings.kimi_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )
    except Exception as exc:
        logger.exception("[AI] Kimi API call failed.")
        raise AIServiceError(f"Kimi provider error: {exc}") from exc

    raw: Optional[str] = response.choices[0].message.content
    if not raw:
        raise AIServiceError("Kimi returned an empty response.")

    return raw.strip()


def _groq_provider(question: str, user_role: str) -> str:
    """
    Groq API provider via OpenAI compatibility layer.

    Groq uses extremely fast LPU inference, ideal for real-time SQL generation.
    Compatible with the exact same OpenAI SDK.

    Raises:
        AIServiceError: On any API or network failure.
    """
    if not settings.groq_api_key:
        raise AIServiceError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or set LLM_PROVIDER=mock."
        )

    try:
        from openai import OpenAI  # lazy import
    except ImportError as exc:
        raise AIServiceError(
            "openai package is not installed. Run: pip install openai"
        ) from exc

    user_prompt = (
        f"Role context: you are a {user_role} in the platform. "
        f"Question: {question}"
    )

    try:
        client = OpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )
    except Exception as exc:
        logger.exception("[AI] Groq API call failed.")
        raise AIServiceError(f"Groq provider error: {exc}") from exc

    raw: Optional[str] = response.choices[0].message.content
    if not raw:
        raise AIServiceError("Groq returned an empty response.")

    return raw.strip()


# ── Output cleaning ───────────────────────────────────────────────────────────

def _clean_llm_output(raw: str) -> str:
    """
    Strip markdown code fences and leading/trailing whitespace from LLM output.

    Some models wrap SQL in ```sql ... ``` — we strip that here.
    The validator will catch anything truly dangerous below.
    """
    # Remove markdown code fences (```sql ... ```, ``` ... ```)
    cleaned = re.sub(r"^```(?:sql)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


def _check_no_placeholders(sql: str) -> None:
    """
    Raise AIServiceError if the SQL contains any bind-parameter placeholders.

    Patterns caught:
      :name         — SQLAlchemy / Databricks named param   e.g. :company_id
      %(name)s      — Python DB-API 2.0 named param
      ?             — positional placeholder (JDBC / sqlite)
      $1, $2 ...    — PostgreSQL positional
      <placeholder> — angle-bracket template

    Any of these would cause a Databricks execution error and indicate the
    LLM failed to embed a real literal value from the user's question.
    """
    _PLACEHOLDER_PATTERNS = [
        r':\w+',            # :company_id  :year  :value
        r'%\(\w+\)s',      # %(company_id)s
        r'(?<![\w])\?(?![\w])',  # bare ?
        r'\$\d+',          # $1  $2
        r'<[^>]+>',        # <placeholder>  <company_id>
    ]
    for pattern in _PLACEHOLDER_PATTERNS:
        match = re.search(pattern, sql)
        if match:
            logger.warning(
                "[AI] LLM produced a placeholder in SQL (pattern=%s match='%s') — rejecting.",
                pattern,
                match.group(0),
            )
            raise AIServiceError(
                f"The AI generated a query with a placeholder ('{match.group(0)}') instead of a "
                f"real value. Please rephrase your question and include the specific value "
                f"(e.g. company ID, year, or quarter) you want to filter on. "
                f"Example: 'Show profit for company C001' instead of 'Show profit for my company'."
            )
