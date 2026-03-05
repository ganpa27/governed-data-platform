"""
app.py — Flask Stage 4 API + UI Layer.

Routes:
  GET  /                            → UI dashboard
  GET  /api/yearly                  → yearly revenue (all companies)
  GET  /api/quarterly               → quarterly revenue (all companies)
  GET  /api/company/<id>            → company-specific yearly report
  GET  /api/company/<id>/quarterly  → company-specific quarterly report
  GET  /api/top-profit              → top 10 companies by profit
  GET  /api/top-revenue             → top 10 companies by revenue
  GET  /api/top-cost                → top 10 companies by cost
  GET  /api/summary                 → platform aggregate totals
  GET  /api/year/<year>             → yearly filtered by year
  GET  /api/quarter/<n>             → quarterly filtered by quarter number
  POST /api/query-router            → NL question → predefined OR Groq AI → Databricks

All endpoints enforce RBAC via the rbac.py module.
Role is read from X-User-Role header.
Company is read from X-User-Company header (for finance_user).
"""
import time as _time

from flask import Flask, request, jsonify, render_template
from db import run_query
from predefined_queries import QUERIES, QUERY_LABELS, route_question
from ai_engine import (
    generate_sql, AIError, SQLValidationError,
    build_governance_report, generate_summary
)
from llm_stub import llm_stub
from rbac import enforce_rbac

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_role():
    """Read the user role from request headers."""
    return request.headers.get("X-User-Role", "admin").lower()


def _get_company():
    """Read the user company from request headers (finance_user only)."""
    return request.headers.get("X-User-Company", "C001").upper()


def _respond(query_key: str, params: dict | None = None) -> dict:
    """Run a predefined query, apply RBAC, and return a standard JSON envelope."""
    sql    = QUERIES[query_key]
    label  = QUERY_LABELS[query_key]
    role   = _get_role()
    company = _get_company()

    t0 = _time.monotonic()
    cols, rows = run_query(sql, params)
    db_ms = int((_time.monotonic() - t0) * 1000)

    # ── Apply RBAC ────────────────────────────────────────────────────────────
    rbac = enforce_rbac(cols, rows, role, company)

    return {
        "status"          : "success",
        "label"           : label,
        "columns"         : rbac["columns"],
        "rows"            : rbac["rows"],
        "rows_returned"   : rbac["rows_returned"],
        "sql"             : sql.strip(),
        "timings"         : {"db_query_ms": db_ms},
        # RBAC metadata (so UI can show it)
        "rbac_applied"    : rbac["rbac_applied"],
        "rbac_role"       : rbac["rbac_role"],
        "rbac_company"    : rbac["rbac_company"],
        "rbac_detail"     : rbac["rbac_detail"],
        "masked_columns"  : rbac["masked_columns"],
        "filtered_reason" : rbac["filtered_reason"],
    }


def _error(message: str, code: int = 400):
    return jsonify({"status": "error", "message": message}), code


# ── UI ────────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("index.html")


# ── API 1: Yearly Revenue ─────────────────────────────────────────────────────

@app.route("/api/yearly")
def api_yearly():
    try:
        return jsonify(_respond("yearly"))
    except Exception as e:
        return _error(str(e), 500)


# ── API 2: Quarterly Revenue ──────────────────────────────────────────────────

@app.route("/api/quarterly")
def api_quarterly():
    try:
        return jsonify(_respond("quarterly"))
    except Exception as e:
        return _error(str(e), 500)


# ── API 3: Company-specific Revenue ──────────────────────────────────────────

@app.route("/api/company/<company_id>")
def api_company(company_id):
    # Whitelist: only allow C + digits format
    import re
    if not re.fullmatch(r"C\d{3,4}", company_id, re.IGNORECASE):
        return _error("Invalid company_id format. Use e.g. C001, C002.")
    try:
        return jsonify(_respond("company", {"company_id": company_id.upper()}))
    except Exception as e:
        return _error(str(e), 500)


# ── API 4: Top Profit ─────────────────────────────────────────────────────────

@app.route("/api/top-profit")
def api_top_profit():
    try:
        return jsonify(_respond("top_profit"))
    except Exception as e:
        return _error(str(e), 500)


# ── API 5: Top Revenue ────────────────────────────────────────────────────────

@app.route("/api/top-revenue")
def api_top_revenue():
    try:
        return jsonify(_respond("top_revenue"))
    except Exception as e:
        return _error(str(e), 500)


# ── API 6: Platform Summary (aggregate totals) ────────────────────────────────

@app.route("/api/summary")
def api_summary():
    try:
        return jsonify(_respond("summary"))
    except Exception as e:
        return _error(str(e), 500)


# ── API 7: Yearly revenue filtered by year ────────────────────────────────────

@app.route("/api/year/<int:year>")
def api_year_filter(year: int):
    if not (2020 <= year <= 2035):
        return _error("year must be between 2020 and 2035.")
    try:
        return jsonify(_respond("year_filter", {"year": str(year)}))
    except Exception as e:
        return _error(str(e), 500)


# ── API 8: Quarterly breakdown for a single company ───────────────────────────

@app.route("/api/company/<company_id>/quarterly")
def api_company_quarterly(company_id):
    import re
    if not re.fullmatch(r"C\d{3,4}", company_id, re.IGNORECASE):
        return _error("Invalid company_id. Use e.g. C001.")
    try:
        return jsonify(_respond("company_quarterly", {"company_id": company_id.upper()}))
    except Exception as e:
        return _error(str(e), 500)


# ── API 9: All companies for a specific quarter (1–4) ─────────────────────────

@app.route("/api/quarter/<int:quarter>")
def api_quarter_filter(quarter: int):
    if quarter not in (1, 2, 3, 4):
        return _error("quarter must be 1, 2, 3, or 4.")
    try:
        return jsonify(_respond("quarter_filter", {"quarter": str(quarter)}))
    except Exception as e:
        return _error(str(e), 500)


# ── API 10: Top 10 by Cost ────────────────────────────────────────────────────

@app.route("/api/top-cost")
def api_top_cost():
    try:
        return jsonify(_respond("top_cost"))
    except Exception as e:
        return _error(str(e), 500)


# ── API 11: Query Router (NL → predefined → Groq AI → Databricks) ────────────

@app.route("/api/query-router", methods=["POST"])
def api_query_router():
    t_total_start = _time.monotonic()

    body      = request.get_json(silent=True) or {}
    question  = (body.get("question") or "").strip()
    user_role = _get_role()
    company   = _get_company()

    if not question:
        return _error("question field is required.")
    if len(question) > 500:
        return _error("Question exceeds maximum length of 500 characters.")

    # ── Step 1: try keyword router first (fast, zero API cost) ───────────────
    t0 = _time.monotonic()
    result = route_question(question, user_role=user_role, company_id=company or None)
    routing_ms = int((_time.monotonic() - t0) * 1000)

    if result["matched"]:
        try:
            data = _respond(result["query_key"], result["params"])
            data["question"]   = question
            data["query_used"] = result["query_key"]
            data["source"]     = "predefined"

            # Measure AI summary generation
            cols = data["columns"]
            rows = data["rows"]

            # Pass RBAC info to AI summary so it knows about masked/filtered data
            gov_status = "ok"
            if data.get("masked_columns"):
                gov_status = "limited"

            t_sum = _time.monotonic()
            ai_summary = generate_summary(
                question, cols, rows,
                governance_status=gov_status,
                masked_columns=data.get("masked_columns"),
                user_role=user_role,
                company_id=company,
            )
            summary_ms = int((_time.monotonic() - t_sum) * 1000)

            data["ai_summary"] = ai_summary

            total_ms = int((_time.monotonic() - t_total_start) * 1000)
            data["timings"]["routing_ms"]    = routing_ms
            data["timings"]["llm_gen_ms"]    = 0
            data["timings"]["ai_summary_ms"] = summary_ms
            data["timings"]["governance_ms"] = 0
            data["timings"]["total_ms"]      = total_ms

            return jsonify(data)
        except Exception as e:
            return _error(str(e), 500)

    # ── Step 2: no predefined match → call Groq AI ────────────────────────────
    import os
    if not os.getenv("GROQ_API_KEY"):
        stub = llm_stub(question)
        return jsonify(stub), 200

    try:
        t_llm = _time.monotonic()
        sql = generate_sql(question, user_role=user_role, company_id=company or None)
        llm_gen_ms = int((_time.monotonic() - t_llm) * 1000)
    except ValueError as e:
        return jsonify({
            "status"     : "llm_required",
            "message"    : str(e),
            "question"   : question,
            "suggestions": [
                "Show yearly revenue",
                "Show quarterly revenue",
                "Top 10 companies by profit",
                "Revenue for C001",
                "Quarter 1 data",
            ],
        }), 200
    except (AIError, SQLValidationError) as e:
        return _error(f"AI engine error: {e}", 503)
    except Exception as e:
        return _error(f"Unexpected AI error: {e}", 500)

    # ── Step 3: execute the validated AI-generated SQL ────────────────────────
    try:
        t_db = _time.monotonic()
        cols, rows = run_query(sql)
        db_ms = int((_time.monotonic() - t_db) * 1000)

        # ── Step 3.5: Apply RBAC to AI-generated query results ────────────────
        rbac = enforce_rbac(cols, rows, user_role, company)
        cols = rbac["columns"]
        rows = rbac["rows"]

        # ── Step 4: Governance Awareness Layer ────────────────────────────────
        t_gov = _time.monotonic()
        gov_report = build_governance_report(question, cols, rows, user_role)
        governance_ms = int((_time.monotonic() - t_gov) * 1000)

        # ── Step 5: AI Summary Generation ─────────────────────────────────────
        t_sum = _time.monotonic()
        gov_status = gov_report["status"]
        if rbac["masked_columns"]:
            gov_status = "limited"
        
        ai_summary = generate_summary(
            question, cols, rows, 
            governance_status=gov_status,
            masked_columns=rbac["masked_columns"],
            user_role=user_role,
            company_id=company or None,
        )
        summary_ms = int((_time.monotonic() - t_sum) * 1000)

        total_ms = int((_time.monotonic() - t_total_start) * 1000)

        return jsonify({
            "status"           : "success",
            "label"            : f"AI Result — {question[:60]}",
            "columns"          : cols,
            "rows"             : rows,
            "rows_returned"    : rbac["rows_returned"],
            "question"         : question,
            "source"           : "groq_ai",
            "sql"              : sql,
            "governance_status": gov_report["status"],
            "explanation"      : gov_report["explanation"],
            "suggestion"       : gov_report["suggestion"],
            "ai_summary"       : ai_summary,
            "timings"          : {
                "routing_ms"   : routing_ms,
                "llm_gen_ms"   : llm_gen_ms,
                "db_query_ms"  : db_ms,
                "governance_ms": governance_ms,
                "ai_summary_ms": summary_ms,
                "total_ms"     : total_ms,
            },
            # RBAC metadata
            "rbac_applied"    : rbac["rbac_applied"],
            "rbac_role"       : rbac["rbac_role"],
            "rbac_company"    : rbac["rbac_company"],
            "rbac_detail"     : rbac["rbac_detail"],
            "masked_columns"  : rbac["masked_columns"],
            "filtered_reason" : rbac["filtered_reason"],
        })
    except Exception as e:
        return _error(f"Query execution failed: {e}", 500)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 Flask Governed API starting on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
