# Governed Data Platform — Talk to Data POC

A production-grade, role-aware financial data platform powered by **Databricks**, **FastAPI**, and **AI (Groq LLaMA 70B)**.

## Architecture

```
User → Flask UI (port 5001)
         ↓
   Intent Router
   ┌──────────────────┐
   │  Predefined API  │  ← Fast, zero LLM cost
   └──────────────────┘
         ↓ (no match)
   ┌──────────────────┐
   │  Groq AI (70B)   │  ← SQL generation
   └──────────────────┘
         ↓
   ┌──────────────────┐
   │  5-Layer SQL     │  ← Security firewall
   │  Firewall        │
   └──────────────────┘
         ↓
   ┌──────────────────┐
   │  Databricks      │  ← Secure Views + RLS
   └──────────────────┘
         ↓
   AI Executive Summary + Follow-up Suggestions
```

## Projects

| Folder | Stack | Description |
|--------|-------|-------------|
| `governed-data-platform/` | FastAPI + Python | Backend API, AI orchestration, SQL validation |
| `flask-governed-api/` | Flask + Python | Frontend dashboard, query router, AI summary |

## Security Features

- **Row-Level Security** — Each role sees only their permitted data
- **Column Masking** — `total_profit` hidden for auditors, more columns hidden for viewers
- **5-Layer SQL Firewall** — Blocks DDL, DML, stacked queries, disallowed tables
- **Placeholder Guard** — Rejects LLM queries with bind parameters (`:company_id`)
- **RBAC** — Role-based access control enforced on every request

## Roles

| Role | Access |
|------|--------|
| Admin / Manager | Full data, all companies |
| Finance User | Own company data only |
| Auditor | All companies, profit masked |
| Viewer | All companies, cost & profit masked |

## Quick Start

```bash
cd governed-data-platform
./start.sh
```

Runs both FastAPI (port 8000) and Flask (port 5001).

## Environment Variables

Copy `.env.example` and fill in your values:

```bash
cp governed-data-platform/.env.example governed-data-platform/.env
cp flask-governed-api/.env.example flask-governed-api/.env
```

Required variables:
- `DATABRICKS_SERVER_HOSTNAME`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_TOKEN`
- `GROQ_API_KEY`

## Tech Stack

- **AI**: Groq LLaMA 3.3 70B Versatile
- **Database**: Databricks (Delta Lake + Unity Catalog)
- **Backend**: FastAPI + Python 3.11
- **Frontend**: Flask + Vanilla JS
- **Security**: Custom RBAC + SQL Firewall + RLS Views
