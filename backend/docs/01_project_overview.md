# 🏛️ Project Overview — Governed Data Platform

---

## 1. What Is This Project?

The **Governed Data Platform** is an enterprise-grade, role-aware financial data access system built on top of **Databricks Unity Catalog**.

It is not just a database. It is not just an API. It is a **complete governance architecture** where:

- Financial data is stored in a protected raw table.
- Business logic transforms it into useful reports (yearly, quarterly metrics).
- Security rules are pushed **into the database itself**, not just the backend.
- Every data access is **audit-logged** for compliance.
- An AI layer allows natural language questions — but every AI-generated query goes through a **5-layer SQL firewall** before touching data.

> **Core philosophy:** Even if the API is compromised, even if the AI generates wrong SQL, unauthorized data cannot be accessed — because the database itself enforces the rules.

---

## 2. Why We Built This (The Problem)

### The Standard Approach (Weak)
Most applications work like this:

```
User → API → Database (full access) → Filter in API code → Show results
```

**Problems with the standard approach:**
- The backend has a "super-user" connection to the database.
- If the backend is compromised, all data is exposed.
- Filtering in API code means the database returns more data than needed.
- No audit trail at the database level.
- AI-generated queries can bypass backend filters.

### Our Approach (Strong)
We built this platform to solve exactly these problems:

```
User → API → Secure View (Database enforces rules) → Only authorized data returned
```

**What this solves:**
- The database enforces who can see what — even before the API touches the data.
- Finance users can only see their own company's data.
- Auditors can see all companies but not profit figures.
- Admins see everything.
- Even if someone bypasses the API and queries the database directly with an auditor's token, profit remains `NULL`.

---

## 3. What This Platform Does

The platform does four core things:

| # | Function | Description |
|---|----------|-------------|
| 1 | **Store raw financial data** | Individual transaction records (revenue, cost per company) |
| 2 | **Aggregate into reports** | Yearly and quarterly totals per company |
| 3 | **Enforce role-based access** | Inside the database itself via secure views |
| 4 | **Log every access** | Full audit trail for compliance |

On top of that, it provides:
- 10 predefined API endpoints for consistent, safe reporting.
- A Natural Language query interface powered by Groq AI (Llama 3).
- A clean, professional web dashboard UI.

---

## 4. High-Level Architecture

The system has two main tiers: **Database Tier** and **Application Tier**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION TIER                               │
│                                                                        │
│   Web Dashboard (HTML/CSS/JS)                                          │
│          ↓                                                             │
│   Flask API (app.py) — 10 endpoints                                   │
│          ↓                          ↓                                  │
│   Predefined Queries          AI Orchestration (Groq Llama-3)          │
│   (predefined_queries.py)     → 5-Layer SQL Firewall                  │
│                               → Governance Awareness Layer             │
│          ↓                          ↓                                  │
│   Databricks Connection (db.py)                                       │
└────────────────────────────┬───────────────────────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────────────────────┐
│                         DATABASE TIER (Databricks)                     │
│                                                                        │
│   governed_platform_catalog                                            │
│   ├── finance_schema                                                   │
│   │   ├── revenue_transactions         ← Raw Data (no direct access)   │
│   │   ├── revenue_yearly_view          ← Aggregation (no direct access)│
│   │   ├── revenue_quarterly_view       ← Aggregation (no direct access)│
│   │   ├── secure_revenue_yearly        ← ONLY exposed view ✅           │
│   │   └── secure_revenue_quarterly     ← ONLY exposed view ✅           │
│   └── governance_schema                                                │
│       ├── users                        ← Who has what role             │
│       └── audit_logs                   ← Every access logged           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Database Layers (Summary)

The database is built in **5 conceptual layers**, each with a specific purpose:

| Layer | Name | What It Does |
|-------|------|--------------|
| 1 | **Raw Data Layer** | Stores individual financial transactions |
| 2 | **Aggregation Layer** | Groups data into yearly/quarterly totals |
| 3 | **Governance Metadata Layer** | Stores users, roles, company mappings |
| 4 | **Policy Enforcement Layer** | Secure views that merge layers 2+3 and apply filtering |
| 5 | **Audit Layer** | Logs every data access event |

---

## 6. Application Layers (Summary)

| Layer | Component | What It Does |
|-------|-----------|--------------|
| 1 | **Flask API** | Routes HTTP requests to database queries |
| 2 | **Predefined Queries** | 10 hardcoded, safe SQL queries |
| 3 | **Keyword Router** | Matches plain English to predefined queries (no AI cost) |
| 4 | **AI Orchestration** | Converts complex NL questions to SQL via Groq |
| 5 | **SQL Firewall** | 5 layers of validation on every AI-generated query |
| 6 | **Governance Awareness** | Post-execution check for masked columns in results |
| 7 | **Web Dashboard UI** | User-facing interface with role selector |

---

## 7. Three User Roles

| Role | See All Companies? | See Profit? |
|------|-------------------|-------------|
| `admin` | ✅ Yes | ✅ Yes |
| `finance_user` | ❌ Own company only | ✅ Yes (own company) |
| `auditor` | ✅ Yes | ❌ No — `NULL` |

These roles are **not enforced in the API code** — they are enforced **inside the Databricks secure views** using `current_user()` at query time.

---

## 8. Data Flow (End to End)

```
1. User opens web dashboard
2. User selects a role (Admin / Finance User / Auditor) in the UI
3. User either:
   a. Clicks a predefined report button, OR
   b. Types a natural language question
4. Flask API receives the request
5. If predefined → runs a hardcoded safe SQL query
   If NL question → tries keyword router first, then Groq AI
6. If AI is used → SQL goes through 5-layer firewall
7. Validated SQL is sent to Databricks
8. Databricks identifies current_user() → looks up users table
9. Secure view applies Row-Level Security and Column Masking
10. Results return to Flask
11. Flask checks for masked columns (Governance Awareness Layer)
12. Results + AI summary sent to dashboard
13. Dashboard renders table + AI explanation
14. If data was masked → Governance Intervention alert shown
```

---

## 9. What Makes This Architecture Strong

| Threat | How It Is Handled |
|--------|------------------|
| API compromise | Database still enforces roles — Secure Views are the gate |
| SQL injection | Predefined queries use no user input in SQL strings |
| AI hallucination | 5-layer firewall validates every AI-generated query |
| Unauthorized profit access | Column masking at DB level — always `NULL` for auditors |
| Cross-company data leak | Row-level filtering inside Secure Views |
| No audit trail | Every access logged in `governance_schema.audit_logs` |
| Missing LIMIT | Every query enforces a row cap — even AI-generated ones |

---

## 10. Project Files Quick Reference

| File | Location | Purpose |
|------|----------|---------|
| `app.py` | `flask-governed-api/` | Main Flask application, all API routes |
| `db.py` | `flask-governed-api/` | Databricks connection helper |
| `predefined_queries.py` | `flask-governed-api/` | All 10 hardcoded SQL queries + keyword router |
| `ai_engine.py` | `flask-governed-api/` | Groq AI pipeline, firewall, governance checker |
| `llm_stub.py` | `flask-governed-api/` | Fallback stub when Groq key is not configured |
| `templates/index.html` | `flask-governed-api/` | Web dashboard UI |
| `static/style.css` | `flask-governed-api/` | Dashboard styles |
| `stage1_governance_architecture.sql` | `flask-governed-api/` | Full Databricks SQL setup script |
| `.env` | `flask-governed-api/` | Databricks + Groq credentials |

---

*Next: See `02_database_architecture.md` for a deep dive into each database layer.*
