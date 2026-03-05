# 🧱 Database Architecture & Layers (Databricks)

---

## 1. Overview

The entire governance and security model of this platform is implemented **inside Databricks Unity Catalog**. The application API is a thin proxy layer — it does not filter data, it does not enforce roles. All of that happens at the database level.

This document walks through every layer of the database, from the very bottom (raw transactions) to the very top (secure views that users actually query).

---

## 2. Databricks Catalog & Schema Structure

We use a single **catalog** with two separate **schemas**:

```
governed_platform_catalog
├── finance_schema        ← Financial data and views
└── governance_schema     ← Security, users, roles, audit logs
```

### Why Two Schemas?

**Business data and security data must never be mixed.**

If both lived in the same schema:
- A compromised backend could accidentally expose user role data.
- There would be no clean separation between "what happened" (finance) and "who is allowed" (governance).
- Maintenance would become messy — a developer working on finance reports should not be able to accidentally edit governance tables.

The separation makes the system:
- **Clearer** — any developer can immediately see what schema does what.
- **Safer** — permissions can be granted at the schema level independently.
- **More maintainable** — governance rules evolve separately from business logic.

---

## 3. Layer 1 — Raw Data Layer (Foundation)

### What It Is
This is the absolute lowest layer. It stores raw, individual financial transactions — one row per transaction. No aggregation. No filtering. No role awareness.

### Table: `finance_schema.revenue_transactions`

```sql
CREATE TABLE IF NOT EXISTS finance_schema.revenue_transactions (
    transaction_id  STRING     PRIMARY KEY,  -- Unique ID for this transaction
    company_id      STRING     NOT NULL,     -- Which company this belongs to (e.g. "C001")
    revenue_amount  DOUBLE     NOT NULL,     -- Money earned in this transaction
    cost_amount     DOUBLE     NOT NULL,     -- Money spent in this transaction
    created_at      TIMESTAMP  NOT NULL,     -- Exact time of the transaction
    region          STRING,                  -- Geographic region (optional)
    currency        STRING                   -- Currency code (optional)
);
```

### What Each Column Means

| Column | Type | Purpose |
|--------|------|---------|
| `transaction_id` | STRING | Unique identifier for this exact financial event |
| `company_id` | STRING | Links the transaction to a tenant company (e.g. `C001`, `C002`) |
| `revenue_amount` | DOUBLE | Dollar amount earned in this transaction |
| `cost_amount` | DOUBLE | Dollar amount spent to generate this revenue |
| `created_at` | TIMESTAMP | Exact datetime — used to group transactions by year and quarter |
| `region` | STRING | Optional geographic tag |
| `currency` | STRING | Optional currency tag |

### Key Properties
- **No role logic.** This table has no concept of users or access rights.
- **No aggregation.** Each row is one financial event, not a monthly or yearly total.
- **Source of truth.** If this table has wrong data, every view above it will have wrong data.

### Security Rule
> **Nobody has direct SELECT access to this table.**

Not the admin. Not the Flask API. Not the AI. Not auditors. The platform strictly operates through the layers above this table.

```sql
-- This access is REVOKED at the schema level:
REVOKE ALL PRIVILEGES ON SCHEMA finance_schema FROM `users`;
```

Think of this as the **accounting ledger** — raw, authoritative, untouched.

---

## 4. Layer 2 — Aggregation Layer (Business Logic)

### What It Is
Raw transactions are useful for forensics but useless for management reports. A CFO doesn't want 10,000 individual rows — they want "total revenue for C001 in 2024."

The aggregation layer creates database **views** (not tables) that compute these totals using `GROUP BY` logic.

### Why Views, Not Tables?
- Views compute results dynamically every time they are queried.
- They always reflect the latest data in `revenue_transactions`.
- No data duplication.
- No scheduled jobs needed to refresh.

### View A: `finance_schema.revenue_yearly_view`

```sql
CREATE OR REPLACE VIEW finance_schema.revenue_yearly_view AS
SELECT
    company_id,
    YEAR(created_at)                           AS year,
    SUM(revenue_amount)                        AS total_revenue,
    SUM(cost_amount)                           AS total_cost,
    SUM(revenue_amount - cost_amount)          AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY
    company_id,
    YEAR(created_at);
```

**Output columns:**

| Column | Meaning |
|--------|---------|
| `company_id` | The tenant company identifier |
| `year` | The calendar year (e.g. 2024) |
| `total_revenue` | Sum of all revenue amounts for this company in this year |
| `total_cost` | Sum of all costs for this company in this year |
| `total_profit` | Calculated as `total_revenue - total_cost` |

### View B: `finance_schema.revenue_quarterly_view`

```sql
CREATE OR REPLACE VIEW finance_schema.revenue_quarterly_view AS
SELECT
    company_id,
    YEAR(created_at)                           AS year,
    QUARTER(created_at)                        AS quarter,
    SUM(revenue_amount)                        AS total_revenue,
    SUM(cost_amount)                           AS total_cost,
    SUM(revenue_amount - cost_amount)          AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY
    company_id,
    YEAR(created_at),
    QUARTER(created_at);
```

This is identical to the yearly view but adds a `quarter` dimension (1, 2, 3, or 4) for finer-grained reporting.

### Key Properties
- **No user awareness.** These views don't know who is querying them.
- **Pure math.** They just compute summaries.
- **Not directly accessible.** Nobody queries these views directly — all access goes through the Secure Views above them.

> Think of this as the **management report layer** — the computed business summaries.

---

## 5. Layer 3 — Governance Metadata Layer (Identity)

### What It Is
This is where **security begins**. This schema does not store financial numbers. It stores **who users are**, **what role they have**, and **which company they belong to**.

### Table A: `governance_schema.users`

```sql
CREATE TABLE IF NOT EXISTS governance_schema.users (
    user_id     STRING   PRIMARY KEY,
    email       STRING   NOT NULL,
    role_name   STRING   NOT NULL,   -- 'admin' | 'finance_user' | 'auditor'
    company_id  STRING               -- NULL for admin/auditor; 'C001' etc. for finance_user
);
```

#### Why This Table Is Critical
When a user (or API token) connects to Databricks and queries a Secure View, Databricks calls `current_user()` — which returns the email address of the authenticated token owner. That email is matched against this `users` table to determine:
1. What role does this person have?
2. If they're a `finance_user`, which company are they allowed to see?

#### Example Rows

| user_id | email | role_name | company_id |
|---------|-------|-----------|------------|
| U001 | admin@platform.com | admin | NULL |
| U002 | alpha@company.com | finance_user | C001 |
| U003 | beta@company.com | finance_user | C002 |
| U999 | ganesh@elliotsystems.com | auditor | NULL |

- `NULL` in `company_id` means the user is not restricted to one company.
- `C001` means the user can only see rows belonging to company `C001`.

### Table B: `governance_schema.audit_logs`

```sql
CREATE TABLE IF NOT EXISTS governance_schema.audit_logs (
    log_id           STRING     PRIMARY KEY,
    user_email       STRING     NOT NULL,
    role_name        STRING     NOT NULL,
    query_type       STRING,              -- e.g. 'yearly', 'top_profit', 'ai_query'
    accessed_object  STRING,              -- e.g. 'secure_revenue_yearly'
    access_timestamp TIMESTAMP  NOT NULL,
    company_context  STRING               -- Which company context was active
);
```

Every time data is accessed, a record is written here. This supports:
- **Compliance audits** — who accessed what and when.
- **Security forensics** — detect unexpected access patterns.
- **Regulatory requirements** — financial platforms must maintain access records.

> Think of this as the **identity and compliance layer** — it knows *who* is querying, not *what* data exists.

---

## 6. Layer 4 — Policy Enforcement Layer (Secure Views)

### What It Is
This is the **most important layer** in the entire architecture.

The Secure Views are the **only objects the API is allowed to query**. They combine:
- Data from the **Aggregation Layer** (Layer 2)
- Identity from the **Governance Layer** (Layer 3)
- And apply **Row-Level Security** and **Column-Level Masking** in real time at query execution.

> The database does not trust the API to filter data correctly. The database does the filtering itself.

### Secure View A: `finance_schema.secure_revenue_yearly`

```sql
CREATE OR REPLACE VIEW finance_schema.secure_revenue_yearly AS
SELECT
    v.company_id,
    v.year,
    v.total_revenue,
    v.total_cost,

    -- COLUMN MASKING: auditors see NULL instead of profit
    CASE
        WHEN u.role_name = 'auditor' THEN NULL
        ELSE v.total_profit
    END AS total_profit

FROM finance_schema.revenue_yearly_view v

-- This JOIN is the key — it maps current_user() to their role
JOIN governance_schema.users u ON u.email = current_user()

WHERE
    -- Admin sees everything
    (u.role_name = 'admin')
    -- Auditor sees all rows (for compliance) but profit is masked above
    OR (u.role_name = 'auditor')
    -- Finance user sees only their company
    OR (
        u.role_name = 'finance_user'
        AND v.company_id = u.company_id
    );
```

### Secure View B: `finance_schema.secure_revenue_quarterly`
Identical logic, but built on top of `revenue_quarterly_view` — adds the `quarter` column and applies the same row filtering and profit masking.

### How the Row Filtering Works (Multi-Tenancy)

When `finance_user` from company `C001` runs a query:
1. `current_user()` returns their email.
2. The JOIN matches them in the `users` table → role = `finance_user`, company_id = `C001`.
3. The `WHERE` clause: `v.company_id = u.company_id` → only rows where `company_id = 'C001'` pass.
4. Even if there are 100 companies in the database, this user sees exactly 1.

When an `auditor` runs the same query:
1. `current_user()` matches → role = `auditor`.
2. The `WHERE` clause: `u.role_name = 'auditor'` → all rows from all companies pass.
3. But the `CASE` statement: `total_profit` resolves to `NULL` for every row.

### How the Column Masking Works
The `CASE/WHEN` logic runs **at the database engine level** during query execution. It does not matter what the API asks for. It does not matter what the AI generates. If the user's role is `auditor`, every value in the `total_profit` column is replaced with `NULL` before the data even leaves Databricks.

---

## 7. Layer 5 — Audit Layer (Compliance Tracking)

Every time the API or AI engine runs a query, the application can record a log entry into `governance_schema.audit_logs`.

### What Gets Logged
- **Who** made the request (email/role from token).
- **What** they requested (endpoint or query type).
- **When** they made it (timestamp).
- **Which object** was accessed (e.g. `secure_revenue_yearly`).
- **Company context** (which company was in scope).

### Why This Matters
In enterprise environments, financial data platforms are subject to compliance regulations (SOC 2, GDPR, financial reporting standards). The audit log is the mechanism that proves:
- "This user accessed this data at this time."
- "No one accessed profit data outside of authorized roles."

---

## 8. Grant & Revoke Summary

```sql
-- Revoke all access to the raw schema (nobody touches raw tables or aggregation views)
REVOKE ALL PRIVILEGES ON SCHEMA finance_schema FROM `users`;
REVOKE ALL PRIVILEGES ON SCHEMA governance_schema FROM `users`;

-- Grant SELECT only on the TWO secure views
GRANT SELECT ON VIEW finance_schema.secure_revenue_yearly TO `users`;
GRANT SELECT ON VIEW finance_schema.secure_revenue_quarterly TO `users`;
```

This means: even if an admin tried to directly query `revenue_transactions`, they would receive a permission denied error. The only path to data is through the secure views.

---

## 9. Layer Summary Table

| Layer | Object | Type | Access? | Purpose |
|-------|--------|------|---------|---------|
| 1 | `revenue_transactions` | Table | ❌ None | Raw financial events |
| 2 | `revenue_yearly_view` | View | ❌ None | Yearly aggregations |
| 2 | `revenue_quarterly_view` | View | ❌ None | Quarterly aggregations |
| 3 | `governance_schema.users` | Table | ❌ None | User-role identity mapping |
| 3 | `governance_schema.audit_logs` | Table | ❌ None | Access audit trail |
| 4 | `secure_revenue_yearly` | View | ✅ API Only | Role-filtered yearly data |
| 4 | `secure_revenue_quarterly` | View | ✅ API Only | Role-filtered quarterly data |

---

*Next: See `03_er_diagram_and_models.md` for an entity-relationship breakdown of how these tables connect.*
