# Governed Data Platform – Backend API

> **Stage 2 of the AI-Governed Role-Aware Data Access Platform**
>
> A secure, enterprise-grade FastAPI backend that enforces role-based access
> control, multi-tenant isolation, SQL governance, and full audit logging on top
> of Databricks Unity Catalog.

---

## Architecture Overview

```
Frontend (React / AI UI)
        │
        ▼
FastAPI Backend  (this project)
  ├── Authentication Layer      ← Bearer token → governance_schema.users
  ├── Option A: Predefined Reports  ← hardcoded SQL, zero injection surface
  ├── Option B: Controlled SQL Engine
  │     ├── SQL Validator (SQLGlot, 5 layers)
  │     └── Audit Logger (2-layer: app log + Databricks table)
  └── Databricks Connector
        │
        ▼
Databricks SQL Warehouse
  └── governed_platform_catalog
        ├── finance_schema
        │     ├── secure_revenue_yearly     ← row filter + column masking
        │     └── secure_revenue_quarterly  ← row filter + column masking
        └── governance_schema
              ├── users
              └── audit_logs
```

---

## Folder Structure

```
governed-data-platform/
│
├── app/
│   ├── main.py                  ← Application entry point
│   ├── core/
│   │   ├── config.py            ← Pydantic settings (reads .env)
│   │   ├── security.py          ← Auth: token resolver + UserContext
│   │   └── database.py          ← Single-point Databricks connector
│   │
│   ├── api/
│   │   ├── predefined.py        ← Option A: /reports/* endpoints
│   │   └── free_sql.py          ← Option B: /execute-query endpoint
│   │
│   ├── services/
│   │   ├── validator.py         ← 5-layer SQLGlot SQL validator
│   │   └── audit.py             ← 2-layer audit logging service
│   │
│   └── models/
│       └── schemas.py           ← Pydantic v2 request/response models
│
├── requirements.txt
├── .env.example                 ← Copy to .env and fill in credentials
└── .gitignore
```

---

## Setup

### 1. Clone and enter the directory

```bash
cd governed-data-platform
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Open .env and fill in real Databricks credentials
```

Required variables:

| Variable | Description |
|---|---|
| `DATABRICKS_SERVER_HOSTNAME` | Your workspace hostname |
| `DATABRICKS_HTTP_PATH` | SQL Warehouse HTTP path |
| `DATABRICKS_TOKEN` | Personal access token |
| `DATABRICKS_CATALOG` | `governed_platform_catalog` |
| `DATABRICKS_SCHEMA` | `finance_schema` |

### 5. Run the development server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## API Endpoints

### Platform

| Method | Path | Description |
|---|---|---|
| GET | `/` | Root / version info |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc UI |

### Option A – Predefined Reports

| Method | Path | Description |
|---|---|---|
| GET | `/reports/yearly-revenue` | Annual revenue report (secure view) |
| GET | `/reports/quarterly-revenue` | Quarterly revenue report (secure view) |

Both endpoints accept an optional `?limit=N` query parameter.

**Authentication**: `Authorization: Bearer <user-email>` (demo mode)

### Option B – Controlled SQL Engine

| Method | Path | Description |
|---|---|---|
| POST | `/execute-query` | Execute a validated SELECT query |

**Request body:**
```json
{
  "query": "SELECT * FROM secure_revenue_quarterly LIMIT 10"
}
```

---

## Security Model

### Role Behaviour

| Role | Row Access | Profit Column |
|---|---|---|
| `admin` | All companies | Visible |
| `finance_user` | Own company only | Visible |
| `auditor` | All companies | Masked (NULL) |

Row filtering and column masking are enforced **inside Databricks** at the
view layer — the backend cannot bypass them.

### SQL Validator (5 Layers – Option B)

1. **Keyword blocklist** – regex check blocks `DROP`, `DELETE`, `UPDATE`, etc.
2. **UNION block** – prevents side-channel leaks across views
3. **AST parse** – SQLGlot parses the query; syntax errors are rejected
4. **Statement type** – only `SELECT` statements pass
5. **View allowlist** – every table/view reference must be in the explicit allowlist (`secure_revenue_yearly`, `secure_revenue_quarterly`)

A query must pass **all five layers** to execute.

### Audit Logging (2 Layers)

1. **Application log** – always written to stdout/file, survives DB outage
2. **Databricks log** – best-effort INSERT into `governance_schema.audit_logs`

Audit is written **before** query execution — even crashed queries are recorded.

---

## Roles & Access Examples

```bash
# Yearly report as admin
curl -H "Authorization: Bearer admin@company.com" \
     http://localhost:8000/reports/yearly-revenue

# Quarterly report as finance user
curl -H "Authorization: Bearer user@acme.com" \
     http://localhost:8000/reports/quarterly-revenue

# Free SQL as power user (allowed)
curl -X POST \
     -H "Authorization: Bearer analyst@company.com" \
     -H "Content-Type: application/json" \
     -d '{"query": "SELECT * FROM secure_revenue_yearly LIMIT 5"}' \
     http://localhost:8000/execute-query

# Free SQL – BLOCKED (raw table access)
curl -X POST \
     -H "Authorization: Bearer analyst@company.com" \
     -H "Content-Type: application/json" \
     -d '{"query": "SELECT * FROM revenue_transactions"}' \
     http://localhost:8000/execute-query
# → 403 Forbidden: Query blocked by governance policy
```

---

## Development Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Complete | FastAPI project + Databricks connection |
| Phase 2 | ✅ Complete | Option A predefined report endpoints |
| Phase 3 | ✅ Complete | 5-layer SQL validator |
| Phase 4 | ✅ Complete | Option B controlled SQL engine |
| Phase 5 | ✅ Complete | 2-layer audit logging |
| Phase 6 | 🔜 Upcoming | AI/NLP-to-SQL integration layer |

---

## Stage 1 (Databricks Layer) Reference

The Databricks objects that back this API:

```sql
-- Secure views (used by all queries)
governed_platform_catalog.finance_schema.secure_revenue_yearly
governed_platform_catalog.finance_schema.secure_revenue_quarterly

-- Governance tables
governed_platform_catalog.governance_schema.users
governed_platform_catalog.governance_schema.audit_logs
```

Security is enforced at both layers:
- **Databricks layer**: view-level row filtering + column masking
- **Backend layer**: authentication + SQL validation + audit logging

---

## Security Principles

> Security > Flexibility

1. Never expose raw tables
2. Always use secure governed views
3. Always validate SQL before execution
4. Always audit before execution
5. Never allow direct DB access in production
6. Every ambiguity in identity → fail loudly (401), never fail silently
