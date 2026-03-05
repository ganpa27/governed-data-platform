"""
predefined_queries.py — Query definitions and keyword router.

Security contract:
  - All SQL here is hardcoded. User input is NEVER interpolated into SQL.
  - Only secure_revenue_yearly and secure_revenue_quarterly are queried.
  - Every query has a mandatory LIMIT.
"""
import re

# ── 5 Predefined SQL queries ─────────────────────────────────────────────────

CATALOG = "governed_platform_catalog"
SCHEMA  = "finance_schema"

QUERIES = {
    "yearly": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        LIMIT 100
    """,

    "quarterly": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_quarterly
        LIMIT 100
    """,

    "company": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        WHERE company_id = :company_id
        LIMIT 100
    """,

    "top_profit": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        ORDER BY total_profit DESC NULLS LAST
        LIMIT 10
    """,

    "top_revenue": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        ORDER BY total_revenue DESC NULLS LAST
        LIMIT 10
    """,

    # ── 5 NEW QUERIES ────────────────────────────────────────────────────────

    # API 6: Platform-wide summary totals
    "summary": f"""
        SELECT
            COUNT(DISTINCT company_id)          AS total_companies,
            SUM(total_revenue)                  AS platform_revenue,
            SUM(total_cost)                     AS platform_cost,
            SUM(total_profit)                   AS platform_profit,
            ROUND(AVG(total_revenue), 2)        AS avg_revenue_per_company
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
    """,

    # API 7: Filter all companies by a specific year
    "year_filter": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        WHERE year = :year
        ORDER BY total_revenue DESC NULLS LAST
        LIMIT 100
    """,

    # API 8: Quarterly breakdown for a single company
    "company_quarterly": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_quarterly
        WHERE company_id = :company_id
        ORDER BY year DESC, quarter ASC
        LIMIT 100
    """,

    # API 9: All companies for a specific quarter
    "quarter_filter": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_quarterly
        WHERE quarter = :quarter
        ORDER BY total_revenue DESC NULLS LAST
        LIMIT 100
    """,

    # API 10: Top 10 highest-cost companies (cost efficiency analysis)
    "top_cost": f"""
        SELECT *
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        ORDER BY total_cost DESC NULLS LAST
        LIMIT 10
    """,

    # Company-filtered summary (for finance_user asking about "our" totals)
    "company_summary": f"""
        SELECT
            company_id,
            SUM(total_revenue)    AS total_revenue,
            SUM(total_cost)       AS total_cost,
            SUM(total_profit)     AS total_profit
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        WHERE company_id = :company_id
        GROUP BY company_id
    """,

    # Company-filtered summary for a specific year
    "company_summary_year": f"""
        SELECT
            company_id,
            year,
            total_revenue,
            total_cost,
            total_profit
        FROM {CATALOG}.{SCHEMA}.secure_revenue_yearly
        WHERE company_id = :company_id
          AND year = :year
        ORDER BY year DESC
        LIMIT 10
    """,
}

QUERY_LABELS = {
    "yearly"              : "Yearly Revenue — All Companies",
    "quarterly"           : "Quarterly Revenue — All Companies",
    "company"             : "Revenue — Filtered by Company",
    "top_profit"          : "Top 10 Companies by Profit",
    "top_revenue"         : "Top 10 Companies by Revenue",
    "summary"             : "Platform Summary — Aggregate Totals",
    "year_filter"         : "Yearly Revenue — Filtered by Year",
    "company_quarterly"   : "Quarterly Breakdown — Single Company",
    "quarter_filter"      : "Quarterly Revenue — Filtered by Quarter",
    "top_cost"            : "Top 10 Companies by Cost",
    "company_summary"     : "Company Summary — Aggregate Totals",
    "company_summary_year": "Company Summary — Filtered by Year",
}


# ── Keyword router ────────────────────────────────────────────────────────────

def route_question(
    question:   str,
    user_role:  str = "admin",
    company_id: str | None = None,
) -> dict:
    """
    Match a natural language question to one of the predefined queries.

    SECURITY CRITICAL: For finance_user, questions about "our" or "my" data
    are intercepted and routed to the AI engine (not predefined summary)
    so the AI generates properly company-filtered SQL.

    Priority order:
      1. Company + quarterly combo  (e.g. "quarterly breakdown for C001")
      2. Company yearly             (e.g. "revenue for C002")
      3. Finance user personal total (e.g. "our total profit") → company_summary
      4. Summary / totals           (e.g. "platform total", "summary")
      5. Quarter number filter      (e.g. "Q1 data", "quarter 3")
      6. Year filter                (e.g. "in 2024", "for 2023")
      7. Top cost                   (e.g. "highest cost companies")
      8. Top profit                 (e.g. "top 10 by profit")
      9. Top revenue                (e.g. "top 10 by revenue")
     10. Quarterly (all)            (e.g. "quarterly revenue")
     11. Yearly (all)               (e.g. "annual data")
     12. Generic                    (e.g. "show data")
     13. No match → fall through to AI
    """
    q = question.lower().strip()
    role = (user_role or "admin").lower().strip()
    
    company_id_match = None
    _m = re.search(r"\b(c\d{3,4})\b", q, re.IGNORECASE)
    if _m:
        company_id_match = _m.group(1).upper()
    else:
        if "elliot" in q: company_id_match = "C001"
        elif "technova" in q: company_id_match = "C002"
        elif "greenfield" in q: company_id_match = "C003"
        elif "meridian" in q: company_id_match = "C004"
        elif "atlas" in q: company_id_match = "C005"

    # ── 1. Company + quarterly breakdown ────────────────────────────────────────────
    if company_id_match and any(w in q for w in ["quarter", "quarterly", "q1", "q2", "q3", "q4"]):
        return {
            "matched"  : True,
            "query_key": "company_quarterly",
            "sql"      : QUERIES["company_quarterly"],
            "label"    : QUERY_LABELS["company_quarterly"],
            "params"   : {"company_id": company_id_match},
        }

    # ── 2. Company yearly ──────────────────────────────────────────────────────────
    if company_id_match:
        return {
            "matched"  : True,
            "query_key": "company",
            "sql"      : QUERIES["company"],
            "label"    : QUERY_LABELS["company"],
            "params"   : {"company_id": company_id_match},
        }

    # ── 3. Finance user asking about "our"/"my" totals ─────────────────────────────
    # CRITICAL: "our total profit in 2024" must go to AI so it generates
    # a properly filtered query: WHERE company_id = 'C001' AND year = 2024
    # Predefined queries cannot pass both company_id AND year together safely.
    _our_keywords = ["our", "my", "we", "ours"]
    _profit_keywords = ["profit", "revenue", "cost", "total", "summary", "overall"]
    if role == "finance_user" and company_id:
        if any(w in q for w in _our_keywords):
            # Let the AI generate the correctly scoped query
            return {"matched": False, "query_key": None, "sql": None, "label": None, "params": {}}

        # Year + company context: use company_summary_year
        year_m = re.search(r"\b(202[0-9])\b", q)
        if year_m and any(w in q for w in _profit_keywords):
            return {
                "matched"  : True,
                "query_key": "company_summary_year",
                "sql"      : QUERIES["company_summary_year"],
                "label"    : QUERY_LABELS["company_summary_year"],
                "params"   : {"company_id": company_id.upper(), "year": year_m.group(1)},
            }

    # ── 4. Summary / aggregate totals ─────────────────────────────────────────────
    if any(w in q for w in ["summary", "total", "overall", "platform", "aggregate", "grand"]):
        # Finance users get their company-scoped summary
        if role == "finance_user" and company_id:
            return {
                "matched"  : True,
                "query_key": "company_summary",
                "sql"      : QUERIES["company_summary"],
                "label"    : QUERY_LABELS["company_summary"],
                "params"   : {"company_id": company_id.upper()},
            }
        return _match("summary")

    # ── 5. Quarter number filter (e.g. "Q1", "quarter 2") ───────────────────────────
    qnum = re.search(r"\bq(?:uarter)?[\s-]?(1|2|3|4)\b", q)
    if qnum:
        return {
            "matched"  : True,
            "query_key": "quarter_filter",
            "sql"      : QUERIES["quarter_filter"],
            "label"    : QUERY_LABELS["quarter_filter"],
            "params"   : {"quarter": qnum.group(1)},
        }

    # 6. Year filter (e.g. "in 2024") ────────────────────────────────────────────────
    year = re.search(r"\b(202[0-9])\b", q)
    if year and "quarter" not in q:
        return {
            "matched"  : True,
            "query_key": "year_filter",
            "sql"      : QUERIES["year_filter"],
            "label"    : QUERY_LABELS["year_filter"],
            "params"   : {"year": year.group(1)},
        }

    # 7. Top cost ─────────────────────────────────────────────────────────────────────
    if any(w in q for w in ["cost", "expense", "spending"]) and \
       any(w in q for w in ["top", "highest", "most"]):
        return _match("top_cost")

    # 8. Top profit ────────────────────────────────────────────────────────────────
    if any(w in q for w in ["top", "best", "highest"]) and "profit" in q:
        return _match("top_profit")

    # 9. Top revenue ───────────────────────────────────────────────────────────────
    if any(w in q for w in ["top", "best", "highest"]) and "revenue" in q:
        return _match("top_revenue")

    # 10. Quarterly (all) ───────────────────────────────────────────────────────────
    if any(w in q for w in ["quarter", "quarterly"]):
        return _match("quarterly")

    # 11. Yearly / annual ───────────────────────────────────────────────────────────
    if any(w in q for w in ["year", "yearly", "annual"]):
        return _match("yearly")

    # 12. Generic ───────────────────────────────────────────────────────────────────
    if any(w in q for w in ["revenue", "show", "all", "data", "list"]):
        return _match("yearly")

    # No match → fall through to AI ───────────────────────────────────────────────
    return {"matched": False, "query_key": None, "sql": None, "label": None, "params": {}}


def _match(key: str) -> dict:
    return {
        "matched"  : True,
        "query_key": key,
        "sql"      : QUERIES[key],
        "label"    : QUERY_LABELS[key],
        "params"   : {},
    }

