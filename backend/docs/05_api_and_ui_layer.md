# 🌐 API & User Interface Layer

---

## 1. What This Document Covers

This document explains the **Application Tier** — everything that sits between the database and the user's browser:

- Flask API backend (`app.py`)
- Database connection helper (`db.py`)
- Predefined SQL queries (`predefined_queries.py`)
- Keyword router for natural language matching
- Web dashboard UI (`templates/index.html` + `static/style.css`)
- How the `X-User-Role` header works
- All 11 API endpoints explained

---

## 2. Flask Application Overview

The Flask application (`flask-governed-api/app.py`) serves as a **thin proxy layer** between the user and the governed database. 

### Critical Principle
> The Flask API does NOT filter data. It does NOT enforce roles. It simply sends queries to Databricks and passes the results back. All security enforcement happens in the database Secure Views.

### Application Start

```python
if __name__ == "__main__":
    print("🚀 Flask Governed API starting on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
```

The app runs on port `5001` to avoid conflicts with other services.

---

## 3. Database Connection (`db.py`)

The `db.py` file handles all communication with Databricks.

### Connection Function

```python
def get_connection():
    return sql.connect(
        server_hostname      = os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path            = os.getenv("DATABRICKS_HTTP_PATH"),
        access_token         = os.getenv("DATABRICKS_TOKEN"),
        _tls_trusted_ca_file = certifi.where(),   # Fixes macOS TLS issues
    )
```

All credentials come from the `.env` file. The `certifi` library ensures proper TLS certificate validation on macOS.

### Query Execution Function

```python
def run_query(sql_text: str, params: dict | None = None) -> tuple[list, list]:
    if params:
        for k, v in params.items():
            sql_text = sql_text.replace(f":{k}", f"'{v}'")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql_text)
        columns = [d[0] for d in cursor.description]
        rows    = [list(row) for row in cursor.fetchall()]
    return columns, rows
```

### Parameters Safety
The `params` dict is used for things like `:company_id` and `:year`. These values come exclusively from the keyword router functions — never from raw user input. The function replaces `:param_name` with the safe extracted value.

---

## 4. Predefined Queries (`predefined_queries.py`)

This file contains **10 hardcoded SQL queries** mapped to API endpoints. These are the safest possible queries because:

- SQL is written by developers, not users.
- User input is never interpolated into SQL strings.
- Every query has a mandatory `LIMIT` clause.
- Every query targets only `secure_revenue_yearly` or `secure_revenue_quarterly`.

### All 10 Queries

| Key | SQL Target | Purpose |
|-----|-----------|---------|
| `yearly` | `SELECT * FROM secure_revenue_yearly LIMIT 100` | All companies, yearly |
| `quarterly` | `SELECT * FROM secure_revenue_quarterly LIMIT 100` | All companies, quarterly |
| `company` | `SELECT * FROM secure_revenue_yearly WHERE company_id = :company_id LIMIT 100` | Single company yearly |
| `top_profit` | `SELECT * FROM secure_revenue_yearly ORDER BY total_profit DESC NULLS LAST LIMIT 10` | Top 10 by profit |
| `top_revenue` | `SELECT * FROM secure_revenue_yearly ORDER BY total_revenue DESC NULLS LAST LIMIT 10` | Top 10 by revenue |
| `summary` | `SELECT COUNT(DISTINCT company_id), SUM(total_revenue), SUM(total_cost), ... FROM secure_revenue_yearly` | Platform totals |
| `year_filter` | `SELECT * FROM secure_revenue_yearly WHERE year = :year ORDER BY total_revenue DESC LIMIT 100` | Filter by year |
| `company_quarterly` | `SELECT * FROM secure_revenue_quarterly WHERE company_id = :company_id ORDER BY year DESC, quarter ASC LIMIT 100` | Single company, quarterly |
| `quarter_filter` | `SELECT * FROM secure_revenue_quarterly WHERE quarter = :quarter ORDER BY total_revenue DESC LIMIT 100` | Filter by quarter number |
| `top_cost` | `SELECT * FROM secure_revenue_yearly ORDER BY total_cost DESC NULLS LAST LIMIT 10` | Top 10 by cost |

---

## 5. Keyword Query Router

When a user types a natural language question in the dashboard, the system first tries to match it to one of the 10 predefined queries using keyword pattern matching. This is faster and costs nothing (no AI API call).

### How It Works

The `route_question()` function receives the user's question and checks patterns in this priority order:

```
Priority 1: Company + quarterly combo   → "quarterly breakdown for C001"
Priority 2: Company yearly              → "revenue for C002"
Priority 3: Summary / totals            → "platform total" or "summary"
Priority 4: Quarter number filter       → "Q1 data" or "quarter 3"
Priority 5: Year filter                 → "in 2024" or "for 2023"
Priority 6: Top cost                    → "highest cost companies"
Priority 7: Top profit                  → "top 10 by profit"
Priority 8: Top revenue                 → "top 10 by revenue"
Priority 9: Quarterly (all)             → "quarterly revenue"
Priority 10: Yearly / annual            → "annual data"
Priority 11: Generic                    → "show data" or "revenue"
Priority 12: No match                   → Falls through to AI (Groq)
```

### Company ID Detection

The router uses a regex pattern to detect company IDs:

```python
company_match = re.search(r"\b(c\d{3,4})\b", q, re.IGNORECASE)
```

This matches patterns like `C001`, `c002`, `C0012` in the user's question.

### Year Detection

```python
year = re.search(r"\b(202[0-9])\b", q)
```

Matches years from 2020 to 2029.

### Why This Matters

- Most user questions are simple and match predefined patterns.
- The keyword router resolves these instantly without calling Groq AI.
- This saves API costs and reduces response latency.
- Only truly complex or unrecognized questions go to the AI engine.

---

## 6. All 11 API Endpoints

### API 1: `GET /api/yearly`
Returns yearly revenue data for all companies.

### API 2: `GET /api/quarterly`
Returns quarterly revenue data for all companies.

### API 3: `GET /api/company/<company_id>`
Returns yearly revenue filtered by a specific company ID.
- Input validation: must match pattern `C` followed by 3-4 digits.

### API 4: `GET /api/top-profit`
Returns top 10 companies ordered by total profit (descending).

### API 5: `GET /api/top-revenue`
Returns top 10 companies ordered by total revenue (descending).

### API 6: `GET /api/summary`
Returns platform-wide aggregate totals (total companies, total revenue, total cost, total profit, average revenue).

### API 7: `GET /api/year/<year>`
Returns yearly data filtered by a specific year.
- Input validation: year must be between 2020 and 2035.

### API 8: `GET /api/company/<company_id>/quarterly`
Returns quarterly breakdown for a specific company.

### API 9: `GET /api/quarter/<quarter>`
Returns data for all companies filtered by a specific quarter (1-4).

### API 10: `GET /api/top-cost`
Returns top 10 companies ordered by total cost (descending).

### API 11: `POST /api/query-router`
The main Natural Language entry point. Accepts a JSON body with a `question` field.

Flow:
1. Try keyword router first (fast, free).
2. If no match and Groq API key configured → call AI engine.
3. If no Groq key → return LLM stub with suggestions.
4. If AI generates SQL → validate through 5-layer firewall → execute → check governance → return results.

---

## 7. The Response Helper (`_respond()`)

All predefined endpoints use a common helper function:

```python
def _respond(query_key: str, params: dict | None = None) -> dict:
    sql   = QUERIES[query_key]
    label = QUERY_LABELS[query_key]
    cols, rows = run_query(sql, params)
    return {
        "status"       : "success",
        "label"        : label,
        "columns"      : cols,
        "rows"         : rows,
        "rows_returned": len(rows),
    }
```

This ensures every API response has a consistent structure.

---

## 8. Web Dashboard UI

### Technology
- **HTML**: `templates/index.html` — single page application
- **CSS**: `static/style.css` — professional enterprise styling
- **JavaScript**: Embedded in `index.html` — handles API calls and rendering
- **Icons**: Lucide icon library (loaded from CDN)
- **Fonts**: Inter from Google Fonts

### Dashboard Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ SIDEBAR                    │ MAIN CONTENT                         │
│                            │                                      │
│ [Elliot Logo]              │ TOPBAR: Title + Role Selector        │
│                            │                                      │
│ REPORTS                    │ QUERY BOX: Natural Language Input     │
│  • Yearly Revenue          │  + Quick-select chips                │
│  • Quarterly Revenue       │                                      │
│  • Platform Summary        │ RESULTS AREA:                        │
│                            │  • Data table with formatted numbers │
│ RANKINGS                   │  • Governance alerts (if masked)     │
│  • Top 10 by Profit        │  • AI Executive Summary              │
│  • Top 10 by Revenue       │                                      │
│  • Top 10 by Cost          │                                      │
│                            │                                      │
│ FILTER BY PERIOD           │                                      │
│  • Year filter             │                                      │
│  • Quarter filter          │                                      │
│                            │                                      │
│ COMPANY LOOKUP             │                                      │
│  • Company yearly          │                                      │
│  • Company quarterly       │                                      │
│                            │                                      │
│ [Databricks Connected]     │                                      │
└──────────────────────────────────────────────────────────────────┘
```

### Role Selector

The top bar contains a dropdown with three roles:
- Role: Admin
- Role: Finance User
- Role: Auditor

When a user selects a role, the `X-User-Role` header is sent with every API request. This header is used by the AI engine for context (e.g., adjusting LIMIT caps), but the **actual security enforcement happens in the database** via `current_user()`.

### AI Summary Display

When results come back, if an AI summary is included in the response, it is displayed below the data table with a smooth typewriter animation effect:

```javascript
function typeWriter() {
    if (i < data.ai_summary.length) {
        currentText += data.ai_summary.charAt(i);
        container.innerHTML = marked.parse(currentText);
        i++;
        setTimeout(typeWriter, speed);
    }
}
```

### Governance Alerts

If the API detects masked columns or restricted access, the UI displays a warning alert:
- **Yellow alert**: "Governance Intervention" — data is partially restricted.
- **Blue alert**: Informational note about masked columns.

### Quick Chips

Below the query input, there are clickable chips for common queries:
- Yearly, Quarterly, Summary, Top Profit, Top Revenue, Top Cost, Year 2024, Q1 Data, C001 Quarterly, C002 Revenue

Clicking a chip auto-fills the query input and immediately sends the request.

---

*Next: See `06_ai_orchestration.md` for the AI pipeline, SQL firewall, and governance awareness layer.*
