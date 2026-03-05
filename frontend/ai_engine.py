"""
ai_engine.py — Groq AI orchestration + Governance Awareness Layer.

Flow:
  User question (+ role)
    → generate_sql()          calls Groq llama-3.3-70b-versatile
    → validate_sql()          5-layer SQL firewall
    → inject_limit()          enforce row cap per role
    → db.run_query()          execute against Databricks
    → build_governance_report() inspect results for masked columns
    → return enriched response with governance metadata

Security principle:
  AI output is UNTRUSTED. Every generated SQL string MUST pass
  validate_sql() before it can ever reach the database.

Governance principle:
  Masked columns (e.g. total_profit = NULL for auditor role) must be
  detected AFTER execution. If an analytical question depends on masked
  data, a governance_limited response is returned — never a misleading
  result.

Configuration (.env):
  GROQ_API_KEY=gsk-...
  GROQ_MODEL=llama-3.3-70b-versatile
  GROQ_BASE_URL=https://api.groq.com/openai/v1
  AI_MAX_TOKENS=500
  AI_TEMPERATURE=0.1
"""

from __future__ import annotations

import os
import re
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv("GROQ_API_KEY",   "")
GROQ_MODEL     = os.getenv("GROQ_MODEL",     "llama-3.3-70b-versatile")
GROQ_BASE_URL  = os.getenv("GROQ_BASE_URL",  "https://api.groq.com/openai/v1")
AI_MAX_TOKENS  = int(os.getenv("AI_MAX_TOKENS",  "500"))
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.1"))

CATALOG = "governed_platform_catalog"
SCHEMA  = "finance_schema"

# ── Role-based row caps ───────────────────────────────────────────────────────
ROLE_ROW_CAPS: dict[str, int] = {
    "admin":        100,
    "manager":      100,
    "finance_user": 50,
    "auditor":      50,
    "viewer":       20,
}
DEFAULT_ROW_CAP = 20

# ── Governance: columns that may be masked per role ───────────────────────────
# These are the columns that secure views return as NULL for restricted roles.
PROFIT_COLS = {"total_profit"}

# Keywords that indicate the user wants an analytical calculation
# that directly depends on profit / margin data.
ANALYTICAL_PROFIT_KEYWORDS = {
    "profit", "margin", "profitability", "loss", "net",
    "lowest profit", "highest profit", "best profit", "worst profit",
    "rank", "ranking",
}

# ── System prompt builder (governance-aware, role-aware, company-aware) ───────
# NOTE: This is now a function, not a constant, so role + company_id are injected
# per-request. This is the critical fix for Row-Level Security enforcement.

COMPANY_NAMES: dict[str, str] = {
    "C001": "Elliot Systems (Technology, Mumbai)",
    "C002": "TechNova Solutions (IT Services, Bangalore)",
    "C003": "GreenField Industries (Manufacturing, Pune)",
    "C004": "Meridian Corp (Finance, Delhi)",
    "C005": "Atlas Dynamics (Automotive, Chennai)",
}


def _build_system_prompt(user_role: str, company_id: str | None) -> str:
    """
    Build a per-request system prompt that includes the user's exact role
    and company so the LLM can generate correctly filtered SQL.

    SECURITY CRITICAL: For finance_user, the company_id is ALWAYS injected
    into the WHERE clause instruction. This ensures the AI never returns
    data belonging to other companies, complementing the app-layer RBAC.
    """
    role_block = _build_role_block(user_role, company_id)

    return f"""You are a SQL generation assistant for a governed financial data platform.

STRICT RULES — you MUST follow these without exception:
1. Generate ONLY a single SELECT statement.
2. You may ONLY query these two views (always use the fully-qualified name):
     - {CATALOG}.{SCHEMA}.secure_revenue_yearly
     - {CATALOG}.{SCHEMA}.secure_revenue_quarterly
3. Never use any other table, view, schema, or database.
4. Never use UNION, JOIN, subqueries, CTEs, or window functions.
5. Never use DROP, DELETE, UPDATE, INSERT, ALTER, CREATE, TRUNCATE, or any DDL/DML.
6. Never access governance_schema, revenue_transactions, users, audit_logs, or companies.
7. Output ONLY the raw SQL query — no explanation, no markdown, no code fences.
8. Always include a LIMIT clause (maximum 100).
9. If the question cannot be answered with the two allowed views, output exactly:
   CANNOT_ANSWER

GOVERNANCE AWARENESS (critical):
- The column `total_profit` may be masked (NULL) for auditor and viewer roles.
- The column `total_cost` may be masked (NULL) for viewer role.
- Do NOT compute derived values from masked columns.
- Generate the SQL to SELECT the raw columns — the governance layer above
  you will detect masking and return an appropriate response.

ALL COMPANY IDs AND NAMES:
  C001 = Elliot Systems (Technology, Mumbai)
  C002 = TechNova Solutions (IT Services, Bangalore)
  C003 = GreenField Industries (Manufacturing, Pune)
  C004 = Meridian Corp (Finance, Delhi)
  C005 = Atlas Dynamics (Automotive, Chennai)

Available columns in {CATALOG}.{SCHEMA}.secure_revenue_yearly:
  company_id VARCHAR, year INT, total_revenue DECIMAL, total_cost DECIMAL,
  total_profit DECIMAL  ← may be NULL for restricted roles

Available columns in {CATALOG}.{SCHEMA}.secure_revenue_quarterly:
  company_id VARCHAR, year INT, quarter INT, total_revenue DECIMAL,
  total_cost DECIMAL, total_profit DECIMAL  ← may be NULL for restricted roles

{role_block}

Security note: output is validated by a 5-layer SQL firewall before execution.
"""


def _build_role_block(user_role: str, company_id: str | None) -> str:
    """
    Build the role-specific instruction block injected into the system prompt.
    This is the most security-critical part of the prompt.
    """
    role = (user_role or "admin").lower().strip()

    if role in ("admin", "manager"):
        return (
            f"CURRENT USER ROLE: {role.upper()}\n"
            f"ACCESS LEVEL: Full access — you may query ALL companies without any WHERE filter."
        )

    elif role == "finance_user":
        cid = (company_id or "C001").upper().strip()
        cname = COMPANY_NAMES.get(cid, cid)
        return (
            f"CURRENT USER ROLE: FINANCE_USER\n"
            f"COMPANY RESTRICTION — THIS IS MANDATORY:\n"
            f"  - The user belongs ONLY to company {cid} ({cname}).\n"
            f"  - You MUST always add WHERE company_id = '{cid}' to EVERY query you generate.\n"
            f"  - NEVER generate a query that returns data for other companies.\n"
            f"  - If the user says 'our', 'my', 'we', it means company {cid} ({cname}).\n"
            f"  - Even for aggregate queries (SUM, COUNT, AVG), always include WHERE company_id = '{cid}'.\n"
            f"  - Example correct query: SELECT year, total_profit FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly WHERE company_id = '{cid}' LIMIT 100"
        )

    elif role == "auditor":
        return (
            f"CURRENT USER ROLE: AUDITOR\n"
            f"ACCESS LEVEL: Read-only access to all companies. "
            f"Note: total_profit is masked (NULL) for this role. "
            f"Do not generate queries that depend on profit calculations."
        )

    elif role == "viewer":
        return (
            f"CURRENT USER ROLE: VIEWER\n"
            f"ACCESS LEVEL: Read-only, restricted. "
            f"Note: total_profit and total_cost are both masked (NULL) for this role."
        )

    else:
        return f"CURRENT USER ROLE: {role.upper()}\nACCESS LEVEL: Restricted."

# ── SQL Firewall ──────────────────────────────────────────────────────────────
_ALLOWED_STMTS   = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_BLOCKED_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|"
    r"UNION|INTO|GRANT|REVOKE|MERGE|CALL|PRAGMA|SHOW|DESCRIBE)\b",
    re.IGNORECASE,
)
_ALLOWED_VIEWS = {
    f"{CATALOG}.{SCHEMA}.secure_revenue_yearly",
    f"{CATALOG}.{SCHEMA}.secure_revenue_quarterly",
}
_BLOCKED_TABLES = re.compile(
    r"\b(revenue_transactions|raw_revenue|audit_logs|users|governance_schema)\b",
    re.IGNORECASE,
)
_STACKED_STMTS = re.compile(r";.*\S", re.DOTALL)


# ── Exceptions ────────────────────────────────────────────────────────────────
class AIError(Exception):
    """Raised when the AI pipeline fails (network, config, empty response)."""

class SQLValidationError(AIError):
    """Raised when generated SQL fails the firewall."""


# ══════════════════════════════════════════════════════════════════════════════
# SQL Firewall
# ══════════════════════════════════════════════════════════════════════════════

def validate_sql(sql: str) -> str:
    """
    5-layer SQL firewall. Raises SQLValidationError if any layer fails.
    Returns the cleaned SQL string if all layers pass.
    """
    cleaned = sql.strip().rstrip(";").strip()

    # Layer 1 — must start with SELECT
    if not _ALLOWED_STMTS.match(cleaned):
        raise SQLValidationError(
            f"Layer 1: Only SELECT statements are permitted. Got: {cleaned[:60]}"
        )

    # Layer 2 — no dangerous SQL keywords
    m = _BLOCKED_KEYWORDS.search(cleaned)
    if m:
        raise SQLValidationError(
            f"Layer 2: Blocked keyword '{m.group()}' detected."
        )

    # Layer 3 — must reference at least one governed view
    sql_lower = cleaned.lower()
    if not any(v.lower() in sql_lower for v in _ALLOWED_VIEWS):
        raise SQLValidationError(
            "Layer 3: Query must target only the governed views "
            "(secure_revenue_yearly or secure_revenue_quarterly)."
        )

    # Layer 4 — no blocked tables or schemas
    bm = _BLOCKED_TABLES.search(cleaned)
    if bm:
        raise SQLValidationError(
            f"Layer 4: Blocked table/schema '{bm.group()}' detected."
        )

    # Layer 5 — no stacked statements
    if _STACKED_STMTS.search(cleaned):
        raise SQLValidationError(
            "Layer 5: Stacked SQL statements (semicolons) are not allowed."
        )

    return cleaned


def inject_limit(sql: str, role: str = "admin") -> str:
    """
    Ensure the query carries a LIMIT clause.
    Cap is role-aware: admins get more rows, auditors fewer.
    """
    if re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return sql
    cap = ROLE_ROW_CAPS.get(role, DEFAULT_ROW_CAP)
    return f"{sql} LIMIT {cap}"


def _clean_llm_output(raw: str) -> str:
    """Strip markdown code fences and surrounding whitespace from LLM output."""
    cleaned = re.sub(r"^```(?:sql)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


# ══════════════════════════════════════════════════════════════════════════════
# Governance Awareness Layer
# ══════════════════════════════════════════════════════════════════════════════

def detect_masked_columns(columns: list[str], rows: list[list]) -> list[str]:
    """
    Inspect query results for columns that are entirely NULL.

    A column that returns NULL for every row indicates it has been masked
    by the secure view based on the user's role (e.g. auditors cannot
    see total_profit).

    Returns a list of column names that are fully masked.
    """
    if not rows:
        return []

    masked = []
    for i, col in enumerate(columns):
        if col.lower() in PROFIT_COLS:
            col_values = [row[i] for row in rows]
            if all(v is None for v in col_values):
                masked.append(col)
    return masked


def detect_analytical_dependency(question: str) -> bool:
    """
    Determine whether the user's question requires an analytical calculation
    that depends on profit / margin data.

    Examples that return True:
      "Which company had the lowest profit margin?"
      "Rank companies by profitability"
      "What is the net profit ranking?"

    Examples that return False:
      "Show all yearly revenue"
      "Which company had the highest total revenue?"
    """
    q = question.lower()
    return any(keyword in q for keyword in ANALYTICAL_PROFIT_KEYWORDS)


def build_governance_report(
    question: str,
    columns:  list[str],
    rows:     list[list],
    user_role: str,
) -> dict:
    """
    Core of the governance awareness layer.

    After query execution, inspect results for masked columns and
    cross-reference with what the question analytically requires.

    Returns a governance dict with:
      - status:          "ok" | "limited"
      - masked_columns:  list of column names that are masked
      - explanation:     human-readable explanation (shown to user)
      - suggestion:      actionable next step for the user
    """
    masked_cols = detect_masked_columns(columns, rows)
    needs_profit_analysis = detect_analytical_dependency(question)

    # ── Governance limited: masked columns affect the requested analysis ───────
    if masked_cols and needs_profit_analysis:
        masked_str = ", ".join(f"`{c}`" for c in masked_cols)
        logger.warning(
            "[Governance] LIMITED — role=%s masked=%s question=%s",
            user_role, masked_cols, question[:80],
        )
        return {
            "status":         "limited",
            "masked_columns": masked_cols,
            "explanation": (
                f"You are not authorized to access {masked_str} data under your current "
                f"role ({user_role.upper()}). Because this query requires restricted data, "
                f"the requested information cannot be provided."
            ),
            "suggestion": (
                "You must request elevated permissions from your system administrator to gain access to this information."
            ),
        }

    # ── Warn if masked but question doesn't analytically depend on it ─────────
    if masked_cols:
        logger.info(
            "[Governance] OK (with note) — role=%s masked=%s", user_role, masked_cols
        )
        return {
            "status":         "ok",
            "masked_columns": masked_cols,
            "explanation": (
                f"Note: column(s) {', '.join(masked_cols)} are masked for your "
                f"role ({user_role!r}). They appear as — in the results below."
            ),
            "suggestion": None,
        }

    # ── All clear ─────────────────────────────────────────────────────────────
    logger.debug("[Governance] OK — role=%s no masking detected", user_role)
    return {
        "status":         "ok",
        "masked_columns": [],
        "explanation":    "All requested columns are available for your role.",
        "suggestion":     None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SQL Generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_sql(
    question:   str,
    user_role:  str = "admin",
    company_id: str | None = None,
) -> str:
    """
    Call Groq to translate a natural language question into validated SQL.

    SECURITY CRITICAL: company_id is now passed and injected into the system
    prompt so the LLM generates correctly filtered SQL for finance_user role.
    Without this, the AI would return data for ALL companies.

    Args:
        question:   Sanitised NL question string.
        user_role:  Caller's role (admin | manager | finance_user | auditor | viewer).
        company_id: Caller's company (e.g. C001) — mandatory for finance_user.

    Returns:
        Validated, limit-injected SQL string ready for db.run_query().

    Raises:
        AIError:            API/config failure.
        SQLValidationError: LLM produced unsafe SQL.
        ValueError:         LLM responded CANNOT_ANSWER.
    """
    if not GROQ_API_KEY:
        raise AIError(
            "GROQ_API_KEY is not set. "
            "Add it to flask-governed-api/.env (get key from https://console.groq.com/keys)"
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AIError("openai package not installed. Run: pip install openai") from exc

    # Build a role-aware + company-aware system prompt per request
    system_prompt = _build_system_prompt(user_role, company_id)

    # User prompt makes role and company explicit a second time for emphasis
    cid_str = f" (company: {company_id})" if company_id else ""
    user_prompt = (
        f"User role: {user_role}{cid_str}\n"
        f"Question: {question}"
    )

    logger.info(
        "[AI] Generating SQL | role=%s company=%s question=%s",
        user_role, company_id or "all", question[:80],
    )

    t0 = time.monotonic()
    try:
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=AI_MAX_TOKENS,
            temperature=AI_TEMPERATURE,
        )
    except Exception as exc:
        logger.exception("[AI] Groq API call failed.")
        raise AIError(f"Groq request failed: {exc}") from exc

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info("[AI] Groq responded in %dms (model=%s)", elapsed_ms, GROQ_MODEL)

    raw: Optional[str] = response.choices[0].message.content
    if not raw or not raw.strip():
        raise AIError("Groq returned an empty response.")

    sql = _clean_llm_output(raw)
    logger.info("[AI] Raw SQL from LLM: %s", sql[:120])

    if sql.upper().strip() == "CANNOT_ANSWER":
        raise ValueError(
            "The AI cannot answer this question using the available governed views. "
            "Please ask about yearly or quarterly revenue, cost, or profit data."
        )

    sql = validate_sql(sql)
    sql = inject_limit(sql, role=user_role)

    logger.info("[AI] Final validated SQL: %s", sql[:120])
    return sql


# ══════════════════════════════════════════════════════════════════════════════
# AI Summary Generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_summary(
    question:          str,
    columns:           list,
    rows:              list,
    governance_status: str = "ok",
    masked_columns:    list[str] = None,
    user_role:         str = "admin",
    company_id:        str | None = None,
) -> dict:
    """
    Generate a rich plain-English summary + 3 follow-up suggestions using Groq.

    Returns a dict:
      {
        "text":      <markdown summary string>,
        "followups": [<question1>, <question2>, <question3>]
      }

    Falls back gracefully if Groq is unavailable.
    """
    import json as _json

    fallback_text = f"The query returned {len(rows)} record(s). Review the table above for details."
    fallback_followups = [
        "Show yearly revenue",
        "Show quarterly breakdown",
        "Top 10 companies by profit",
    ]

    if not rows:
        return {
            "text": "The query returned no matching records for the given criteria.",
            "followups": fallback_followups,
        }

    sample = rows[:10]

    # ── Pre-resolve company IDs → names so LLM never sees raw IDs ──
    col_lower = [c.lower() for c in columns]
    def _resolve_row(row):
        resolved = []
        for i, val in enumerate(row):
            if col_lower[i] == "company_id" and isinstance(val, str):
                resolved.append(COMPANY_NAMES.get(val.upper(), val))
            else:
                resolved.append(val)
        return resolved

    # Replace company_id column name with "Company" in header
    display_columns = [
        "Company" if c.lower() == "company_id" else c
        for c in columns
    ]
    header = " | ".join(display_columns)
    row_lines = "\n".join(
        " | ".join(str(v) if v is not None else "—" for v in _resolve_row(row))
        for row in sample
    )
    data_block = f"Columns: {header}\n{row_lines}"
    if len(rows) > 10:
        data_block += f"\n... ({len(rows) - 10} more rows not shown)"

    # Build context-aware role/company preamble (use name, NEVER raw ID)
    role_context = ""
    role = (user_role or "admin").lower().strip()
    if role == "finance_user" and company_id:
        cname = COMPANY_NAMES.get(company_id.upper(), company_id.upper())
        role_context = (
            f"IMPORTANT CONTEXT: This data belongs exclusively to {cname}. "
            f"Always refer to this company as '{cname}' — never use internal codes.\n\n"
        )
    elif role == "auditor":
        role_context = (
            "IMPORTANT CONTEXT: The user is an auditor — profit data is restricted.\n\n"
        )

    security_note = ""
    if masked_columns:
        security_note = (
            f"\nSECURITY NOTE: Columns {', '.join(masked_columns)} are hidden for this role. "
            f"Mention this briefly but summarize available data.\n"
        )

    summary_prompt = (
        f"{role_context}"
        f'Original question: "{question}"\n\n'
        f"Data returned ({len(rows)} rows):\n{data_block}\n"
        f"{security_note}\n"
        "Instructions:\n"
        "1. Write a detailed, accurate financial analysis summary using markdown (bold, bullets).\n"
        "2. Calculate totals, growth rates, and % changes ACCURATELY from the exact numbers.\n"
        "3. Do NOT repeat the table row-by-row — highlight key insights only.\n"
        "4. IMPORTANT: NEVER use internal company codes like C001, C002, C003, C004, C005.\n"
        "   Always use the full company name (e.g. 'Elliot Systems', 'TechNova Solutions').\n"
        "5. NEVER expose internal system identifiers, role codes, or technical keys in the summary.\n"
        "6. After the summary, output exactly this separator on its own line: ---FOLLOWUPS---\n"
        "7. Then list exactly 3 specific follow-up questions a business analyst would ask next.\n"
        "   Each question on its own line, numbered: 1. ... 2. ... 3. ...\n"
        "   Follow-up questions must also use company NAMES, never codes like C001.\n"
    )

    if not GROQ_API_KEY:
        return {"text": fallback_text, "followups": fallback_followups}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, timeout=15.0)
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise financial data analyst for an enterprise data platform. "
                        "You always follow the output format instructions exactly. "
                        "Use accurate arithmetic — never estimate. "
                        "Output the summary in markdown, then the separator ---FOLLOWUPS---, "
                        "then exactly 3 numbered follow-up questions. Nothing else."
                    ),
                },
                {"role": "user", "content": summary_prompt},
            ],
            max_tokens=1000,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        logger.info("[AI] Summary raw: %s", raw[:120])

        # Split on delimiter
        if "---FOLLOWUPS---" in raw:
            parts    = raw.split("---FOLLOWUPS---", 1)
            summary  = parts[0].strip()
            fq_block = parts[1].strip() if len(parts) > 1 else ""
        else:
            # Fallback: use the whole thing as summary
            summary  = raw
            fq_block = ""

        # Parse numbered follow-ups  (1. ... 2. ... 3. ...)
        followups = []
        if fq_block:
            import re as _re
            for m in _re.finditer(r"\d+\.\s*(.+?)(?=\n\d+\.|$)", fq_block, _re.DOTALL):
                q = m.group(1).strip()
                if q:
                    followups.append(q)
        if not followups:
            followups = fallback_followups

        return {
            "text":      summary or fallback_text,
            "followups": followups[:3],
        }

    except Exception as exc:
        logger.warning("[AI] Summary generation failed: %s", exc)
        return {"text": fallback_text, "followups": fallback_followups}






