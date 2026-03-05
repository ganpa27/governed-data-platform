# 🗄️ Database Architecture — Complete Reference

> **Governed Data Platform · Databricks Unity Catalog**
> Last updated: 26 Feb 2026 · Stage 2

---

## Table of Contents

1. [Overview](#1-overview)
2. [Catalog & Schema Structure](#2-catalog--schema-structure)
3. [Table: `companies`](#3-table-companies)
4. [Table: `revenue_transactions`](#4-table-revenue_transactions)
5. [Table: `users`](#5-table-users)
6. [Table: `audit_logs`](#6-table-audit_logs)
7. [View: `revenue_yearly_view`](#7-view-revenue_yearly_view)
8. [View: `revenue_quarterly_view`](#8-view-revenue_quarterly_view)
9. [View: `secure_revenue_yearly` 🔒](#9-view-secure_revenue_yearly-)
10. [View: `secure_revenue_quarterly` 🔒](#10-view-secure_revenue_quarterly-)
11. [RBAC Matrix — 5 Roles Explained](#11-rbac-matrix--5-roles-explained)
12. [Column-Level Security (CLS)](#12-column-level-security-cls)
13. [Row-Level Security (RLS)](#13-row-level-security-rls)
14. [How `current_user()` Works](#14-how-current_user-works)
15. [Application-Level RBAC (rbac.py)](#15-application-level-rbac-rbacpy)
16. [Data Flow: Query → Table → View → Secure View → User](#16-data-flow)
17. [Entity-Relationship Diagram](#17-entity-relationship-diagram)
18. [Sample Data: What Each Role Sees](#18-sample-data-what-each-role-sees)
19. [SQL Reference: All CREATE Statements](#19-sql-reference)
20. [Permissions & Grants](#20-permissions--grants)
21. [Quick Reference Card](#21-quick-reference-card)

---

## 1. Overview

This platform stores **financial revenue data** for multiple companies and enforces **governance** (who can see what) using a layered architecture inside **Databricks Unity Catalog**.

### Key Design Principles

| Principle | How We Implement It |
|-----------|-------------------|
| **Separation of Concerns** | Business data (`finance_schema`) is completely separate from governance data (`governance_schema`) |
| **Defense in Depth** | Security is enforced at **3 levels**: Databricks secure views → Application RBAC → UI restrictions |
| **Least Privilege** | Users can ONLY access secure views. Raw tables, aggregation views, and governance tables are all blocked |
| **Audit Everything** | Every data access is logged in `audit_logs` for compliance |
| **Multi-Tenancy** | Finance users from different companies share the same tables but see only their own data |

### Architecture Layers

```
Layer 1: Raw Data          → revenue_transactions (protected, no direct access)
Layer 2: Aggregation       → revenue_yearly_view, revenue_quarterly_view (math only)
Layer 3: Governance Meta   → users, companies, audit_logs
Layer 4: Policy Enforcement→ secure_revenue_yearly, secure_revenue_quarterly (🔒 ONLY these are exposed)
Layer 5: Application RBAC  → rbac.py (mirrors DB rules at app level)
```

---

## 2. Catalog & Schema Structure

```
governed_platform_catalog/          ← Unity Catalog (top level)
│
├── finance_schema/                 ← Business data & views
│   ├── companies                   ← Company master data
│   ├── revenue_transactions        ← Raw financial transactions (PROTECTED)
│   ├── revenue_yearly_view         ← Aggregated yearly (PROTECTED)
│   ├── revenue_quarterly_view      ← Aggregated quarterly (PROTECTED)
│   ├── secure_revenue_yearly   🔒  ← EXPOSED — enforces RBAC
│   └── secure_revenue_quarterly🔒  ← EXPOSED — enforces RBAC
│
└── governance_schema/              ← Security & compliance data
    ├── users                       ← Who has what role + company mapping
    └── audit_logs                  ← Every data access recorded
```

### Why Two Schemas?

| Schema | Purpose | Who Can Access |
|--------|---------|---------------|
| `finance_schema` | All financial data: raw transactions, aggregations, secure views | Only secure views are granted to users |
| `governance_schema` | Security configuration: user roles, audit trail | Only the system/admin; never exposed to regular queries |

**Critical**: After setup, we run `REVOKE ALL PRIVILEGES` on both schemas, then `GRANT SELECT` only on the two secure views. This means even if someone knows the table names, they **cannot** query them directly.

---

## 3. Table: `companies`

> **Location**: `governed_platform_catalog.finance_schema.companies`
> **Purpose**: Master data for all companies in the platform. Gives human-readable names to company IDs.

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `company_id` | STRING | ❌ PRIMARY KEY | Unique identifier (e.g., `C001`) |
| `company_name` | STRING | ❌ NOT NULL | Human-readable name (e.g., "Elliot Systems") |
| `industry` | STRING | ✅ | Industry sector |
| `country` | STRING | ✅ | Country of operation |
| `created_at` | TIMESTAMP | ✅ (default: now) | When the record was created |
| `is_active` | BOOLEAN | ✅ (default: TRUE) | Whether company is currently active |

### Current Data (5 Companies)

| company_id | company_name | industry | country |
|------------|-------------|----------|---------|
| C001 | **Elliot Systems** | Technology | India |
| C002 | **TechNova Solutions** | IT Services | India |
| C003 | **GreenField Industries** | Manufacturing | India |
| C004 | **Meridian Corp** | Finance | India |
| C005 | **Atlas Dynamics** | Automotive | India |

### Why This Table Exists

- **Before**: We only had `company_id` (C001, C002...) in transactions. Nobody knew what C003 meant.
- **After**: We can join with this table to show "GreenField Industries" instead of "C003".
- **Demo value**: When presenting, you can say "GreenField Industries had the highest manufacturing revenue" instead of "C003 had the highest".

### Relationships

```
companies.company_id ──1:N──→ revenue_transactions.company_id
companies.company_id ──1:N──→ users.company_id (for finance_user role)
```

---

## 4. Table: `revenue_transactions`

> **Location**: `governed_platform_catalog.finance_schema.revenue_transactions`
> **Purpose**: Raw financial transaction data. This is the **source of truth** for all revenue, cost, and profit numbers.
> **Access**: 🚫 **NO DIRECT ACCESS** — blocked by REVOKE. Only accessible through secure views.

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `transaction_id` | STRING | ❌ PRIMARY KEY | Unique ID (e.g., `T001`) |
| `company_id` | STRING | ❌ NOT NULL | Which company this transaction belongs to |
| `transaction_date` | DATE | ✅ | The business date of the transaction |
| `revenue_type` | STRING | ✅ | Type: `Product`, `Service`, or `Subscription` |
| `region` | STRING | ✅ | City/region (Mumbai, Delhi, Bangalore, etc.) |
| `revenue_amount` | DOUBLE | ❌ NOT NULL | Money earned (in INR) |
| `cost_amount` | DOUBLE | ❌ NOT NULL | Money spent (in INR) |
| `profit_amount` | DOUBLE | ✅ | Pre-calculated profit (`revenue - cost`) |
| `currency` | STRING | ✅ (default: INR) | Currency code |
| `created_at` | TIMESTAMP | ❌ NOT NULL | When the transaction was recorded |

### Current Data Summary (40 Transactions)

| Company | 2023 Txns | 2024 Txns | Total |
|---------|-----------|-----------|-------|
| C001 — Elliot Systems | 4 | 4 | 8 |
| C002 — TechNova Solutions | 4 | 4 | 8 |
| C003 — GreenField Industries | 4 | 4 | 8 |
| C004 — Meridian Corp | 4 | 4 | 8 |
| C005 — Atlas Dynamics | 4 | 4 | 8 |
| **Total** | **20** | **20** | **40** |

### Revenue Types

| Type | What It Means | Example |
|------|-------------|---------|
| `Product` | One-time product sale | Software license, manufactured goods |
| `Service` | Consulting/implementation | IT consulting, maintenance contract |
| `Subscription` | Recurring revenue | SaaS subscription, annual plan |

### Why This Table Is Protected

This table contains **raw, individual transaction details**. If exposed:
- A finance user from Company A could see Company B's individual deals
- An auditor could see exact profit per transaction (they should only see aggregated data with profit masked)
- Anyone could figure out deal sizes, client patterns, and competitive intelligence

**Solution**: Nobody queries this table directly. The aggregation views (`revenue_yearly_view`, `revenue_quarterly_view`) summarize it, and the secure views add RBAC on top.

---

## 5. Table: `users`

> **Location**: `governed_platform_catalog.governance_schema.users`
> **Purpose**: Maps Databricks login emails to roles and company ownership. This is the **single source of truth** for access control.

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `user_id` | STRING | ❌ PRIMARY KEY | Unique user ID (e.g., `U001`) |
| `full_name` | STRING | ❌ NOT NULL | Human-readable name |
| `email` | STRING | ❌ NOT NULL | Databricks login email — matched by `current_user()` |
| `role_name` | STRING | ❌ NOT NULL | One of: `admin`, `manager`, `finance_user`, `auditor`, `viewer` |
| `company_id` | STRING | ✅ | Only set for `finance_user` — defines which company they belong to |
| `is_active` | BOOLEAN | ✅ (default: TRUE) | Can be set to FALSE to revoke access |
| `created_at` | TIMESTAMP | ✅ (default: now) | When the user was created |

### Current Users (6 Users, 5 Roles)

| user_id | full_name | email | role_name | company_id |
|---------|-----------|-------|-----------|------------|
| U001 | **Ganesh Shinde** | ganesh.shinde@elliotsystems.com | 👑 `admin` | — |
| U002 | **Priya Sharma** | priya.sharma@elliotsystems.com | 📊 `manager` | — |
| U003 | **Rahul Mehta** | rahul.mehta@elliotsystems.com | 🏢 `finance_user` | C001 |
| U004 | **Anita Desai** | anita.desai@technova.com | 🏢 `finance_user` | C002 |
| U005 | **Vikram Joshi** | vikram.joshi@compliance.com | 🔍 `auditor` | — |
| U006 | **Sara Khan** | sara.khan@investor.com | 👁 `viewer` | — |

### How Each User Behaves

| User | Story | What They See |
|------|-------|--------------|
| **Ganesh** (Admin) | Platform owner. Needs to see everything for debugging and management. | All 5 companies, all columns |
| **Priya** (Manager) | VP of Operations. Needs full visibility for strategic decisions. | All 5 companies, all columns |
| **Rahul** (Finance) | Finance analyst at Elliot Systems. Only needs his own company's data. | Only C001 rows, all columns |
| **Anita** (Finance) | Finance analyst at TechNova. Only needs her own company's data. | Only C002 rows, all columns |
| **Vikram** (Auditor) | External compliance auditor. Must verify costs but profit is confidential. | All companies, **profit masked** |
| **Sara** (Viewer) | External investor. Only needs revenue overview, no financial details. | All companies, **cost + profit masked** |

### Important: `company_id` is NULL for non-finance roles

- `admin`, `manager`, `auditor`, `viewer` → `company_id = NULL` (they see ALL companies)
- `finance_user` → `company_id = 'C001'` or `'C002'` etc. (they see ONLY their company)

This NULL vs. specific-value distinction is what drives Row-Level Security.

---

## 6. Table: `audit_logs`

> **Location**: `governed_platform_catalog.governance_schema.audit_logs`
> **Purpose**: Records every data access for compliance and forensic analysis.

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `log_id` | STRING | ❌ PRIMARY KEY | Unique log entry ID |
| `user_email` | STRING | ❌ NOT NULL | Who accessed the data |
| `role_name` | STRING | ❌ NOT NULL | What role they had at the time |
| `query_type` | STRING | ✅ | Type of query (SELECT, NL_QUERY, etc.) |
| `accessed_object` | STRING | ✅ | Which view/table was queried |
| `access_timestamp` | TIMESTAMP | ❌ NOT NULL | Exact time of access |
| `company_context` | STRING | ✅ | Which company's data was accessed (if applicable) |

### Why Audit Logs Matter

- **Compliance**: Prove who accessed what data and when
- **Security**: Detect unauthorized access patterns
- **Debugging**: Trace issues back to specific queries
- **Accountability**: Every action has a paper trail

---

## 7. View: `revenue_yearly_view`

> **Location**: `governed_platform_catalog.finance_schema.revenue_yearly_view`
> **Purpose**: Aggregates raw transactions into yearly summaries per company.
> **Access**: 🚫 NOT directly accessible. Used internally by secure views.

### SQL Definition

```sql
CREATE OR REPLACE VIEW finance_schema.revenue_yearly_view AS
SELECT
    company_id,
    YEAR(created_at)                     AS year,
    SUM(revenue_amount)                  AS total_revenue,
    SUM(cost_amount)                     AS total_cost,
    SUM(revenue_amount - cost_amount)    AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY company_id, YEAR(created_at);
```

### Output Columns

| Column | Type | Description |
|--------|------|-------------|
| `company_id` | STRING | Company identifier |
| `year` | INT | Calendar year (2023, 2024) |
| `total_revenue` | DOUBLE | Sum of all `revenue_amount` for that company+year |
| `total_cost` | DOUBLE | Sum of all `cost_amount` for that company+year |
| `total_profit` | DOUBLE | `total_revenue - total_cost` |

### Current Output (10 rows)

| company_id | year | total_revenue | total_cost | total_profit |
|------------|------|---------------|------------|--------------|
| C001 | 2023 | ₹9,00,000 | ₹4,90,000 | ₹4,10,000 |
| C001 | 2024 | ₹12,50,000 | ₹6,85,000 | ₹5,65,000 |
| C002 | 2023 | ₹6,15,000 | ₹3,45,000 | ₹2,70,000 |
| C002 | 2024 | ₹8,25,000 | ₹4,40,000 | ₹3,85,000 |
| C003 | 2023 | ₹13,40,000 | ₹8,80,000 | ₹4,60,000 |
| C003 | 2024 | ₹16,40,000 | ₹10,15,000 | ₹6,25,000 |
| C004 | 2023 | ₹7,45,000 | ₹4,70,000 | ₹2,75,000 |
| C004 | 2024 | ₹9,25,000 | ₹5,90,000 | ₹3,35,000 |
| C005 | 2023 | ₹18,50,000 | ₹12,60,000 | ₹5,90,000 |
| C005 | 2024 | ₹23,30,000 | ₹15,30,000 | ₹8,00,000 |

### Why This View Exists Separately

- **Separation of concerns**: The math (SUM, GROUP BY) is separated from the security logic (CASE, WHERE, JOIN)
- **Reusability**: The same aggregation is used by both the yearly and quarterly secure views
- **Performance**: Databricks can optimize this view independently

---

## 8. View: `revenue_quarterly_view`

> **Location**: `governed_platform_catalog.finance_schema.revenue_quarterly_view`
> **Purpose**: Same as yearly view, but broken down by quarter.
> **Access**: 🚫 NOT directly accessible.

### SQL Definition

```sql
CREATE OR REPLACE VIEW finance_schema.revenue_quarterly_view AS
SELECT
    company_id,
    YEAR(created_at)    AS year,
    QUARTER(created_at) AS quarter,
    SUM(revenue_amount)                  AS total_revenue,
    SUM(cost_amount)                     AS total_cost,
    SUM(revenue_amount - cost_amount)    AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY company_id, YEAR(created_at), QUARTER(created_at);
```

### Output Columns

Same as `revenue_yearly_view` plus:

| Column | Type | Description |
|--------|------|-------------|
| `quarter` | INT | Quarter number (1=Jan-Mar, 2=Apr-Jun, 3=Jul-Sep, 4=Oct-Dec) |

---

## 9. View: `secure_revenue_yearly` 🔒

> **Location**: `governed_platform_catalog.finance_schema.secure_revenue_yearly`
> **Purpose**: THE entry point for all yearly revenue queries. Enforces both **Row-Level Security** and **Column-Level Security**.
> **Access**: ✅ This is one of only **2 objects** that users can query.

### SQL Definition

```sql
CREATE OR REPLACE VIEW finance_schema.secure_revenue_yearly AS
SELECT
    v.company_id,
    v.year,
    v.total_revenue,
    -- COLUMN MASKING: cost (hidden for viewer)
    CASE
        WHEN u.role_name = 'viewer' THEN NULL
        ELSE v.total_cost
    END AS total_cost,
    -- COLUMN MASKING: profit (hidden for auditor + viewer)
    CASE
        WHEN u.role_name IN ('auditor', 'viewer') THEN NULL
        ELSE v.total_profit
    END AS total_profit
FROM finance_schema.revenue_yearly_view v
-- IDENTITY: maps current Databricks login to a role
JOIN governance_schema.users u ON u.email = current_user()
WHERE
    -- ROW-LEVEL SECURITY:
    (u.role_name IN ('admin', 'manager', 'auditor', 'viewer'))
    OR (u.role_name = 'finance_user' AND v.company_id = u.company_id);
```

### Line-by-Line Explanation

| Line | What It Does | Why |
|------|-------------|-----|
| `SELECT v.company_id, v.year, v.total_revenue` | Always visible columns | Every role can see company ID, year, and revenue |
| `CASE WHEN u.role_name = 'viewer' THEN NULL ELSE v.total_cost END` | **Column Masking (CLS)** for cost | Viewers (investors) should not see cost structure |
| `CASE WHEN u.role_name IN ('auditor','viewer') THEN NULL ELSE v.total_profit END` | **Column Masking (CLS)** for profit | Auditors verify costs, not profit. Viewers see revenue only |
| `JOIN governance_schema.users u ON u.email = current_user()` | **Identity Bridge** | Connects Databricks login to our role table |
| `WHERE u.role_name IN ('admin','manager','auditor','viewer')` | **Row Filter** — full access roles | These roles see ALL companies |
| `OR (u.role_name = 'finance_user' AND v.company_id = u.company_id)` | **Row Filter** — finance restriction | Finance users see ONLY their company |

---

## 10. View: `secure_revenue_quarterly` 🔒

> Same logic as `secure_revenue_yearly`, but includes the `quarter` column.
> **Access**: ✅ The second of the 2 exposed objects.

The SQL is identical except it reads from `revenue_quarterly_view` and includes `v.quarter` in the SELECT.

---

## 11. RBAC Matrix — 5 Roles Explained

### Visual Matrix

```
                 ┌─────────┬─────────┬─────────┬─────────┬─────────┐
                 │  Admin  │ Manager │ Finance │ Auditor │ Viewer  │
                 │ (Ganesh)│ (Priya) │ (Rahul) │ (Vikram)│ (Sara)  │
┌────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Rows Visible   │   ALL   │   ALL   │ OWN CO. │   ALL   │   ALL   │
├────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ total_revenue  │    ✅   │    ✅   │    ✅   │    ✅   │    ✅   │
├────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ total_cost     │    ✅   │    ✅   │    ✅   │    ✅   │   ❌    │
├────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ total_profit   │    ✅   │    ✅   │    ✅   │   ❌    │   ❌    │
└────────────────┴─────────┴─────────┴─────────┴─────────┴─────────┘

✅ = Visible     ❌ = Masked (shows as NULL / "—" in UI)
```

### Role Descriptions

#### 👑 Admin (`admin`)
- **Who**: Platform owner (Ganesh Shinde)
- **Purpose**: Full system administration, debugging, data verification
- **Row Access**: ALL companies, ALL years
- **Column Access**: ALL columns visible
- **Use Case**: "I need to see everything to manage the platform"

#### 📊 Manager (`manager`)
- **Who**: Senior leadership (Priya Sharma)
- **Purpose**: Strategic decision-making across all business units
- **Row Access**: ALL companies, ALL years
- **Column Access**: ALL columns visible
- **Use Case**: "As VP, I need the full financial picture for all companies"
- **Difference from Admin**: Same data access, but different purpose. In a production system, admin might have write access too.

#### 🏢 Finance User (`finance_user`)
- **Who**: Company-level finance team (Rahul Mehta → C001, Anita Desai → C002)
- **Purpose**: Day-to-day financial analysis for their own company
- **Row Access**: **ONLY their company's rows** (e.g., Rahul sees only C001)
- **Column Access**: ALL columns visible (they can see their own company's profit)
- **Use Case**: "I only need Elliot Systems' data for my quarterly report"
- **Multi-tenancy**: Two finance users querying the same table see completely different data

#### 🔍 Auditor (`auditor`)
- **Who**: External compliance officer (Vikram Joshi)
- **Purpose**: Verify cost structures and revenue figures for compliance
- **Row Access**: ALL companies (needs cross-company view for audit)
- **Column Access**: Revenue ✅, Cost ✅, **Profit ❌ MASKED**
- **Use Case**: "I need to verify costs are legitimate, but profit margin is board-confidential"
- **Why mask profit?**: Profit = Revenue - Cost. If an auditor could see profit, they'd know the exact margin. Some organizations treat margins as the highest-sensitivity data.

#### 👁 Viewer (`viewer`)
- **Who**: External stakeholder / investor (Sara Khan)
- **Purpose**: High-level revenue overview only
- **Row Access**: ALL companies
- **Column Access**: Revenue ✅, **Cost ❌ MASKED**, **Profit ❌ MASKED**
- **Use Case**: "As an investor, I can see top-line revenue but not the cost structure or margins"
- **Why mask both?**: An investor knowing cost structure could infer operational efficiency, vendor dependencies, etc.

---

## 12. Column-Level Security (CLS)

CLS is implemented using SQL `CASE` statements inside the secure views.

### How It Works

```sql
-- In the secure view:
CASE
    WHEN u.role_name = 'viewer' THEN NULL      -- Sara sees NULL
    ELSE v.total_cost                           -- Everyone else sees the real value
END AS total_cost
```

### Masking Rules

| Column | Visible To | Masked For | Mask Value |
|--------|-----------|------------|------------|
| `total_revenue` | ALL roles | Nobody | — |
| `total_cost` | admin, manager, finance_user, auditor | `viewer` | `NULL` |
| `total_profit` | admin, manager, finance_user | `auditor`, `viewer` | `NULL` |

### In the UI

When a column is masked, it appears as **"—"** (em dash) in the table. The RBAC card above the table tells the user exactly which columns are masked and why.

---

## 13. Row-Level Security (RLS)

RLS is implemented using the `WHERE` clause in the secure views.

### How It Works

```sql
WHERE
    -- These roles see ALL rows:
    (u.role_name IN ('admin', 'manager', 'auditor', 'viewer'))
    -- Finance users see ONLY their company:
    OR (u.role_name = 'finance_user' AND v.company_id = u.company_id)
```

### Example: Same Query, Different Results

**Query**: `SELECT * FROM secure_revenue_yearly`

| User | Role | company_id in users table | Rows Returned |
|------|------|---------------------------|---------------|
| Ganesh | admin | NULL | 10 (all 5 companies × 2 years) |
| Priya | manager | NULL | 10 (all) |
| Rahul | finance_user | C001 | 2 (C001 × 2 years only) |
| Anita | finance_user | C002 | 2 (C002 × 2 years only) |
| Vikram | auditor | NULL | 10 (all) |
| Sara | viewer | NULL | 10 (all) |

### Multi-Tenancy in Action

Rahul (Elliot Systems) and Anita (TechNova) both query the **same table**, but:
- **Rahul sees**: C001 | 2023 | ₹9L and C001 | 2024 | ₹12.5L
- **Anita sees**: C002 | 2023 | ₹6.15L and C002 | 2024 | ₹8.25L

They have **zero visibility** into each other's data. This is multi-tenancy at the database level.

---

## 14. How `current_user()` Works

### The Identity Bridge

```
Databricks Login Email ──→ current_user() ──→ JOIN governance_schema.users ──→ role_name + company_id
```

### Step by Step

1. A user logs into Databricks (or connects via a service token)
2. Databricks knows their email (e.g., `ganesh.shinde@elliotsystems.com`)
3. The secure view calls `current_user()` which returns this email
4. The `JOIN` matches this email to the `governance_schema.users` table
5. From the match, we get `role_name` (e.g., `admin`) and `company_id` (e.g., `NULL`)
6. The `WHERE` clause and `CASE` statements use these values to filter rows and mask columns

### The Service Token Problem

In our Flask app, ALL queries go through a **single Databricks service token** (Ganesh's admin token). So `current_user()` always returns `ganesh.shinde@elliotsystems.com` = admin.

**Solution**: We have `rbac.py` at the application level that mirrors the exact same rules. The UI sends the selected role via `X-User-Role` header, and the app applies the same filtering/masking before returning results.

This means security is enforced at **two layers**:
1. **Databricks level** (secure views) — for direct SQL access
2. **Application level** (rbac.py) — for the Flask web app

---

## 15. Application-Level RBAC (`rbac.py`)

Since the Flask app uses a single service token, we enforce RBAC in Python:

```python
from rbac import enforce_rbac

# After getting data from Databricks:
rbac_result = enforce_rbac(
    columns=["company_id", "year", "total_revenue", "total_cost", "total_profit"],
    rows=[["C001", 2024, 1250000, 685000, 565000], ...],
    role="auditor",        # from X-User-Role header
    company_id="C001"      # from X-User-Company header (finance_user only)
)

# rbac_result["rows"] → profit is masked to None
# rbac_result["masked_columns"] → ["total_profit"]
```

### Where It's Applied

| Endpoint | RBAC Applied? |
|----------|--------------|
| `GET /api/yearly` | ✅ via `_respond()` |
| `GET /api/quarterly` | ✅ via `_respond()` |
| `GET /api/company/<id>` | ✅ via `_respond()` |
| `GET /api/top-profit` | ✅ via `_respond()` |
| `GET /api/top-revenue` | ✅ via `_respond()` |
| `GET /api/top-cost` | ✅ via `_respond()` |
| `GET /api/summary` | ✅ via `_respond()` |
| `GET /api/year/<year>` | ✅ via `_respond()` |
| `GET /api/quarter/<n>` | ✅ via `_respond()` |
| `POST /api/query-router` (predefined) | ✅ via `_respond()` |
| `POST /api/query-router` (AI-generated) | ✅ via `enforce_rbac()` |

**Every single API endpoint** passes through RBAC enforcement. There is no way to get unfiltered data from the API.

---

## 16. Data Flow

### Path 1: Sidebar Button Click (e.g., "Yearly Revenue")

```
User clicks "Yearly Revenue" (as Auditor role)
    │
    ▼
Frontend sends GET /api/yearly
    with header: X-User-Role: auditor
    │
    ▼
app.py → _respond("yearly")
    │
    ├─→ Runs SQL: SELECT * FROM secure_revenue_yearly LIMIT 100
    │       → Databricks returns ALL data (admin token)
    │
    ├─→ enforce_rbac(cols, rows, role="auditor")
    │       → Masks total_profit to NULL for every row
    │
    └─→ Returns JSON with masked data + rbac_detail
    │
    ▼
Frontend renders table with "—" in profit column
    + Shows amber RBAC card: "🔍 Auditor — profit masked"
```

### Path 2: Natural Language Query (via AI)

```
User types "Show revenue for Elliot Systems" (as Finance User, C002)
    │
    ▼
Frontend sends POST /api/query-router
    with headers: X-User-Role: finance_user, X-User-Company: C002
    body: { "question": "Show revenue for Elliot Systems" }
    │
    ▼
app.py → route_question() → no keyword match
    │
    ├─→ generate_sql() → Groq AI writes:
    │     SELECT * FROM secure_revenue_yearly WHERE company_id = 'C001' LIMIT 100
    │
    ├─→ validate_sql() → 5-layer firewall passes ✅
    │
    ├─→ run_query(sql) → Databricks returns C001 data (admin token sees it)
    │
    ├─→ enforce_rbac(cols, rows, role="finance_user", company_id="C002")
    │       → FILTERS OUT C001 rows (Anita is C002, not C001!)
    │       → Returns EMPTY result
    │
    └─→ Returns: "0 rows accessible. Finance user restricted to C002."
```

**This is critical**: Even though the AI generated SQL for C001, the RBAC layer filtered it out because Anita (C002) asked the question. She cannot see C001's data.

---

## 17. Entity-Relationship Diagram

```
┌──────────────────────┐       ┌───────────────────────────┐
│     companies        │       │    revenue_transactions    │
├──────────────────────┤       ├───────────────────────────┤
│ PK company_id ───────┼──1:N──│ FK company_id             │
│    company_name      │       │ PK transaction_id         │
│    industry          │       │    transaction_date       │
│    country           │       │    revenue_type           │
│    is_active         │       │    region                 │
│    created_at        │       │    revenue_amount         │
└──────────┬───────────┘       │    cost_amount            │
           │                   │    profit_amount          │
           │                   │    currency               │
           │1:N                │    created_at             │
           │                   └─────────────┬─────────────┘
           │                                 │ Aggregated by
┌──────────┴───────────┐       ┌─────────────┴─────────────┐
│       users          │       │   revenue_yearly_view     │
├──────────────────────┤       ├───────────────────────────┤
│ PK user_id           │       │    company_id             │
│    full_name         │       │    year                   │
│    email ────────────┼──┐    │    total_revenue          │
│    role_name         │  │    │    total_cost             │
│ FK company_id        │  │    │    total_profit           │
│    is_active         │  │    └─────────────┬─────────────┘
│    created_at        │  │                  │ Secured by
└──────────────────────┘  │    ┌─────────────┴─────────────┐
                          │    │ secure_revenue_yearly  🔒  │
                          │    ├───────────────────────────┤
                          └────│ JOIN on current_user()    │
                               │ WHERE role-based filter   │
                               │ CASE column masking       │
                               └───────────────────────────┘
```

---

## 18. Sample Data: What Each Role Sees

### Query: `SELECT * FROM secure_revenue_yearly WHERE year = 2024`

#### 👑 Ganesh (Admin) — 5 rows, all columns

| company_id | year | total_revenue | total_cost | total_profit |
|------------|------|---------------|------------|--------------|
| C001 | 2024 | 12,50,000 | 6,85,000 | **5,65,000** |
| C002 | 2024 | 8,25,000 | 4,40,000 | **3,85,000** |
| C003 | 2024 | 16,40,000 | 10,15,000 | **6,25,000** |
| C004 | 2024 | 9,25,000 | 5,90,000 | **3,35,000** |
| C005 | 2024 | 23,30,000 | 15,30,000 | **8,00,000** |

#### 📊 Priya (Manager) — Same as Admin

*(Identical output — manager has full access)*

#### 🏢 Rahul (Finance, C001) — 1 row only

| company_id | year | total_revenue | total_cost | total_profit |
|------------|------|---------------|------------|--------------|
| C001 | 2024 | 12,50,000 | 6,85,000 | **5,65,000** |

#### 🏢 Anita (Finance, C002) — 1 row only

| company_id | year | total_revenue | total_cost | total_profit |
|------------|------|---------------|------------|--------------|
| C002 | 2024 | 8,25,000 | 4,40,000 | **3,85,000** |

#### 🔍 Vikram (Auditor) — 5 rows, profit masked

| company_id | year | total_revenue | total_cost | total_profit |
|------------|------|---------------|------------|--------------|
| C001 | 2024 | 12,50,000 | 6,85,000 | **—** |
| C002 | 2024 | 8,25,000 | 4,40,000 | **—** |
| C003 | 2024 | 16,40,000 | 10,15,000 | **—** |
| C004 | 2024 | 9,25,000 | 5,90,000 | **—** |
| C005 | 2024 | 23,30,000 | 15,30,000 | **—** |

#### 👁 Sara (Viewer) — 5 rows, cost + profit masked

| company_id | year | total_revenue | total_cost | total_profit |
|------------|------|---------------|------------|--------------|
| C001 | 2024 | 12,50,000 | **—** | **—** |
| C002 | 2024 | 8,25,000 | **—** | **—** |
| C003 | 2024 | 16,40,000 | **—** | **—** |
| C004 | 2024 | 9,25,000 | **—** | **—** |
| C005 | 2024 | 23,30,000 | **—** | **—** |

---

## 19. SQL Reference

All SQL statements are in `stage2_governance_architecture.sql`. Key statements:

### Create Companies Table
```sql
CREATE TABLE IF NOT EXISTS finance_schema.companies (
    company_id   STRING  PRIMARY KEY,
    company_name STRING  NOT NULL,
    industry     STRING,
    country      STRING,
    created_at   TIMESTAMP DEFAULT current_timestamp(),
    is_active    BOOLEAN DEFAULT TRUE
);
```

### Create Users Table
```sql
CREATE TABLE IF NOT EXISTS governance_schema.users (
    user_id    STRING  PRIMARY KEY,
    full_name  STRING  NOT NULL,
    email      STRING  NOT NULL,
    role_name  STRING  NOT NULL,  -- admin|manager|finance_user|auditor|viewer
    company_id STRING,            -- NULL for admin/manager/auditor/viewer
    is_active  BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT current_timestamp()
);
```

### Create Transactions Table
```sql
CREATE TABLE IF NOT EXISTS finance_schema.revenue_transactions (
    transaction_id STRING PRIMARY KEY,
    company_id     STRING NOT NULL,
    transaction_date DATE,
    revenue_type   STRING,
    region         STRING,
    revenue_amount DOUBLE NOT NULL,
    cost_amount    DOUBLE NOT NULL,
    profit_amount  DOUBLE,
    currency       STRING DEFAULT 'INR',
    created_at     TIMESTAMP NOT NULL
);
```

---

## 20. Permissions & Grants

After creating everything, we lock it down:

```sql
-- Remove ALL access to raw schemas
REVOKE ALL PRIVILEGES ON SCHEMA finance_schema     FROM `users`;
REVOKE ALL PRIVILEGES ON SCHEMA governance_schema   FROM `users`;

-- Grant ONLY on the secure views (the only 2 objects anyone can query)
GRANT SELECT ON VIEW finance_schema.secure_revenue_yearly    TO `users`;
GRANT SELECT ON VIEW finance_schema.secure_revenue_quarterly TO `users`;
```

### What This Means

| Object | Can Users Query It? | Why? |
|--------|-------------------|------|
| `finance_schema.revenue_transactions` | ❌ NO | Raw data is protected |
| `finance_schema.companies` | ❌ NO | Internal reference only |
| `finance_schema.revenue_yearly_view` | ❌ NO | Aggregation without security |
| `finance_schema.revenue_quarterly_view` | ❌ NO | Aggregation without security |
| `finance_schema.secure_revenue_yearly` | ✅ YES | Has RBAC built in |
| `finance_schema.secure_revenue_quarterly` | ✅ YES | Has RBAC built in |
| `governance_schema.users` | ❌ NO | Security config must be hidden |
| `governance_schema.audit_logs` | ❌ NO | Compliance data is protected |

---

## 21. Quick Reference Card

### For Developers

```
Catalog:    governed_platform_catalog
Schemas:    finance_schema, governance_schema
Safe Views: secure_revenue_yearly, secure_revenue_quarterly
DO NOT query: revenue_transactions, companies, users, audit_logs
```

### For Demo Presenters

```
1. Start as 👑 Admin → "Show yearly revenue" → See all 5 companies, all numbers
2. Switch to 🔍 Auditor → Same query → Profit column shows "—"
3. Switch to 👁 Viewer → Same query → Cost AND Profit show "—"
4. Switch to 🏢 Finance (C001) → Same query → Only Elliot Systems visible
5. Change company to C002 → Same query → Only TechNova visible
6. Back to 📊 Manager → Everything is back
```

### For Security Auditors

```
✅ RLS enforced at DB level (secure views) + App level (rbac.py)
✅ CLS enforced at DB level (CASE/WHEN) + App level (rbac.py)
✅ Raw tables blocked (REVOKE ALL PRIVILEGES)
✅ Only 2 objects exposed (secure views)
✅ All access logged (audit_logs table)
✅ AI-generated SQL validated (5-layer firewall)
✅ Identity bridge: current_user() → users table → role + company
```

---

*Document generated for the Governed Data Platform project. For setup instructions, see `docs/07_databricks_setup.md`.*
