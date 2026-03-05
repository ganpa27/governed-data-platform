# 🔄 Complete Data Flow — End to End

---

## 1. What This Document Covers

This is the final summary document. It traces a complete user request from the moment they click a button in the dashboard, all the way through the database and back to the rendered result.

---

## 2. The Two Request Paths

Every user request takes one of two paths:

### Path A: Predefined Query (Fast)
```
User clicks sidebar button OR keyword router matches
    → Hardcoded SQL from predefined_queries.py
    → Sent to Databricks via db.py
    → Secure View applies RLS + CLS
    → Results returned
    → AI summary generated
    → Dashboard renders table + summary
```

### Path B: AI-Powered Query (Complex)
```
User types question that doesn't match keywords
    → Groq AI generates SQL
    → 5-layer SQL firewall validates
    → LIMIT injected based on role
    → Sent to Databricks via db.py
    → Secure View applies RLS + CLS
    → Governance Awareness checks for masked columns
    → AI summary generated (or blocked if governance limited)
    → Dashboard renders results + governance alerts
```

---

## 3. Complete Path A Walkthrough

**User action:** Clicks "Yearly Revenue" button in sidebar.

```
Step 1:  User clicks "Yearly Revenue" button in sidebar
             ↓
Step 2:  JavaScript sends GET /api/yearly to Flask
             ↓
Step 3:  Flask route api_yearly() calls _respond("yearly")
             ↓
Step 4:  _respond() looks up QUERIES["yearly"]:
         "SELECT * FROM governed_platform_catalog.finance_schema.secure_revenue_yearly LIMIT 100"
             ↓
Step 5:  run_query(sql) in db.py:
         - Opens Databricks connection using token from .env
         - Executes the SQL
             ↓
Step 6:  Inside Databricks:
         - secure_revenue_yearly view activates
         - Calls current_user() → returns email of token owner
         - JOINs users table → finds role
         - WHERE clause filters rows based on role
         - CASE/WHEN masks total_profit if role = auditor
         - Returns filtered/masked result set
             ↓
Step 7:  db.py receives (columns, rows) from Databricks
             ↓
Step 8:  Flask builds JSON response:
         {
           "status": "success",
           "label": "Yearly Revenue — All Companies",
           "columns": ["company_id", "year", "total_revenue", "total_cost", "total_profit"],
           "rows": [[...], [...], ...],
           "rows_returned": 4
         }
             ↓
Step 9:  If AI summary is enabled → Groq summarizes the data
             ↓
Step 10: JSON response sent back to browser
             ↓
Step 11: JavaScript receives response:
         - Hides empty state
         - Renders data table with formatted numbers
         - Shows AI summary with typewriter animation
         - If columns are masked → shows governance alert
```

---

## 4. Complete Path B Walkthrough

**User action:** Types "Compare Q1 vs Q3 revenue for C001 in 2024" and clicks Ask.

```
Step 1:  User types question and clicks Ask
             ↓
Step 2:  JavaScript sends POST /api/query-router with:
         { "question": "Compare Q1 vs Q3 revenue for C001 in 2024" }
         Header: X-User-Role: admin
             ↓
Step 3:  Flask route api_query_router() receives the request
         - Extracts question + user_role from request
             ↓
Step 4:  Tries keyword router first: route_question(question)
         - Detects "C001" (company match)
         - Detects "Q1" and "Q3" (quarter references)
         - But "Q1 vs Q3" is ambiguous — no single predefined match
         - Returns: { "matched": False }
             ↓
Step 5:  Keyword router failed → checks if GROQ_API_KEY exists
         - GROQ_API_KEY is set → proceed to AI engine
             ↓
Step 6:  generate_sql() called:
         - Builds prompt: "User role: admin\nQuestion: Compare Q1 vs Q3..."
         - Sends to Groq API (llama-3.3-70b-versatile)
         - Groq generates SQL:
           SELECT * FROM governed_platform_catalog.finance_schema.secure_revenue_quarterly
           WHERE company_id = 'C001' AND year = 2024 AND quarter IN (1, 3) 
           ORDER BY quarter LIMIT 100
             ↓
Step 7:  SQL Firewall validates:
         Layer 1: Starts with SELECT ✅
         Layer 2: No blocked keywords ✅
         Layer 3: References secure_revenue_quarterly ✅
         Layer 4: No blocked schemas/tables ✅
         Layer 5: No stacked statements ✅
             ↓
Step 8:  LIMIT check: SQL already has LIMIT 100 ✅
             ↓
Step 9:  run_query(sql) sends to Databricks
             ↓
Step 10: Inside Databricks (identical to Path A):
         - secure_revenue_quarterly activates
         - current_user() → email → users table → role
         - Filters rows + masks columns based on role
         - Returns only C001 Q1 and Q3 data for 2024
             ↓
Step 11: Governance Awareness Layer:
         - detect_masked_columns() → checks if total_profit is all NULL
         - If admin → profit values present → no masking detected
         - detect_analytical_dependency() → "revenue" doesn't trigger profit flag
         - build_governance_report() → status: "ok"
             ↓
Step 12: AI Summary Generation:
         - Sends results to Groq (llama-3.1-8b-instant)
         - Groq generates: "C001 showed strong Q3 performance with..."
             ↓
Step 13: Flask builds complete response:
         {
           "status": "success",
           "label": "AI Result — Compare Q1 vs Q3 revenue for C001 in 2024",
           "columns": [...],
           "rows": [...],
           "source": "groq_ai",
           "sql": "SELECT * FROM ...",
           "governance_status": "ok",
           "ai_summary": "C001 showed strong Q3 performance..."
         }
             ↓
Step 14: Dashboard renders:
         - Data table with Q1 and Q3 rows
         - AI summary with typewriter effect
         - No governance alerts (status is "ok")
```

---

## 5. Governance-Blocked Path Walkthrough

**User action:** Auditor token asks "Which company had the highest profit margin?"

```
Step 1-8: Same as Path B — AI generates SQL, firewall validates
             ↓
Step 9:  Databricks executes against secure_revenue_yearly
         - current_user() → auditor role
         - WHERE: auditor → all rows pass
         - CASE: auditor → total_profit = NULL for ALL rows
             ↓
Step 10: Results returned to Flask:
         columns: [company_id, year, total_revenue, total_cost, total_profit]
         rows: [["C001", 2024, 700000, 400000, None],
                ["C002", 2024, 300000, 150000, None], ...]
             ↓
Step 11: Governance Awareness Layer:
         - detect_masked_columns() → total_profit is ALL NULL → ["total_profit"]
         - detect_analytical_dependency("highest profit margin") → TRUE
         - build_governance_report() → status: "limited"
             ↓
Step 12: AI Summary is BLOCKED. Replaced with:
         "⚠️ Access Denied: You are not authorized to gain this information."
             ↓
Step 13: Response includes:
         {
           "governance_status": "limited",
           "explanation": "You are not authorized to access total_profit data...",
           "suggestion": "Request elevated permissions from your administrator.",
           "ai_summary": "⚠️ Access Denied..."
         }
             ↓
Step 14: Dashboard renders:
         - Yellow "Governance Intervention" alert
         - Access denied message
         - No misleading AI analysis
```

---

## 6. Layer Summary — All Security Points

```
                User Request
                     │
                     ▼
            ┌─────────────────┐
            │  UI Layer        │ Role selector (UI only, not enforced)
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
            │  Keyword Router  │ Pattern match → predefined queries
            └────────┬────────┘
                     │ (if no match)
                     ▼
            ┌─────────────────┐
            │  AI Engine       │ Groq generates SQL
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
  SECURITY  │  SQL Firewall    │ 5 validation layers
  POINT 1   │  (Application)   │ Blocks unsafe SQL before execution
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
  SECURITY  │  Secure Views    │ Row-Level Security + Column Masking
  POINT 2   │  (Database)      │ Enforced by Databricks at query time
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
  SECURITY  │  Governance      │ Detects masked columns in results
  POINT 3   │  Awareness       │ Blocks AI from analyzing masked data
            └────────┬────────┘
                     │
                     ▼
              Final Response
```

Three independent security points. Each one can stop unauthorized access independently.

---

## 7. Full Docs Index

| # | File | Description |
|---|------|-------------|
| 01 | `01_project_overview.md` | Executive summary, architecture diagram, project files |
| 02 | `02_database_architecture.md` | Database layers, tables, views, grants |
| 03 | `03_er_diagram_and_models.md` | Entity relationships, data models, execution walkthroughs |
| 04 | `04_governance_and_security.md` | RBAC roles, RLS, CLS, multi-tenancy, defense model |
| 05 | `05_api_and_ui_layer.md` | Flask API, 11 endpoints, keyword router, dashboard UI |
| 06 | `06_ai_orchestration.md` | Groq AI pipeline, 5-layer firewall, governance awareness |
| 07 | `07_databricks_setup.md` | Databricks configuration, tokens, .env, troubleshooting |
| 08 | `08_data_flow_and_summary.md` | End-to-end flow diagrams, governance-blocked path |

---

## 8. Key Concepts to Study Further

To deeply understand the database concepts used in this platform:

| Concept | What It Means |
|---------|---------------|
| **Table vs View** | A table stores data on disk. A view is a saved query that runs dynamically. |
| **GROUP BY** | Aggregates rows (e.g., SUM revenue by company and year) |
| **JOIN** | Combines rows from two tables based on a matching column |
| **Row-Level Security** | Filtering rows based on who is querying |
| **Column Masking** | Hiding specific column values based on role |
| **Multi-Tenancy** | Multiple companies sharing one database, isolated by company_id |
| **Audit Logging** | Recording every data access for compliance |
| **Schema Separation** | Keeping business data and security data in different schemas |
| **Principle of Least Privilege** | Users get only the minimum access they need |
| **GRANT / REVOKE** | SQL commands to give or remove permissions |

---

*This completes the documentation for the Governed Data Platform.*
