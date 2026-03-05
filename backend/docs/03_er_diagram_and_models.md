# 📊 ER Diagram & Data Models

---

## 1. What This Document Covers

This document explains how the different tables and views in the database **relate to each other** and how the **data flows** from raw transactions all the way to the governed results seen by users.

Understanding the ER (Entity-Relationship) model is essential for understanding why the Secure Views work the way they do — they are fundamentally a join-based relationship between financial data and governance identity data.

---

## 2. Entity Overview

The platform has **7 core entities** across 2 schemas:

| Entity | Schema | Type | Role |
|--------|--------|------|------|
| `revenue_transactions` | `finance_schema` | Table | Raw financial source of truth |
| `revenue_yearly_view` | `finance_schema` | View | Yearly business aggregations |
| `revenue_quarterly_view` | `finance_schema` | View | Quarterly business aggregations |
| `users` | `governance_schema` | Table | User identity and role mapping |
| `audit_logs` | `governance_schema` | Table | Access compliance records |
| `secure_revenue_yearly` | `finance_schema` | Secure View | Policy-enforced yearly data output |
| `secure_revenue_quarterly` | `finance_schema` | Secure View | Policy-enforced quarterly data output |

---

## 3. ER Relationship Diagram

```
governance_schema                       finance_schema
─────────────────                       ──────────────

┌────────────────────┐                 ┌──────────────────────────────┐
│      users         │                 │    revenue_transactions       │
├────────────────────┤                 ├──────────────────────────────┤
│ PK user_id         │                 │ PK transaction_id            │
│    email      ─────┼──┐              │    company_id                │
│    role_name       │  │              │    revenue_amount            │
│    company_id      │  │              │    cost_amount               │
└────────────────────┘  │              │    created_at                │
                        │              │    region                    │
                        │              │    currency                  │
                        │              └────────────┬─────────────────┘
                        │                           │
                        │               GROUP BY company_id,
                        │               YEAR(created_at),
                        │               QUARTER(created_at)
                        │                           │
                        │              ┌────────────▼─────────────────┐
                        │              │   revenue_yearly_view         │
                        │              ├──────────────────────────────┤
                        │              │   company_id                  │
                        │              │   year                        │
                        │              │   total_revenue               │
                        │              │   total_cost                  │
                        │              │   total_profit                │
                        │              └────────────┬─────────────────┘
                        │                           │
                        │              ┌────────────▼─────────────────┐
                        │              │  revenue_quarterly_view       │
                        │              ├──────────────────────────────┤
                        │              │   company_id                  │
                        │              │   year                        │
                        │              │   quarter                     │
                        │              │   total_revenue               │
                        │              │   total_cost                  │
                        │              │   total_profit                │
                        │              └────────────┬─────────────────┘
                        │                           │
                        │    JOIN on                 │
                        │    u.email = current_user()│
                        │                           │
                        └───────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────────┐
                    │  secure_revenue_yearly              │
                    │  secure_revenue_quarterly           │
                    ├───────────────────────────────────┤
                    │ Applies:                           │
                    │ • Row-Level Security (WHERE)       │
                    │ • Column Masking (CASE/WHEN)       │
                    │ → Returns ONLY what user can see   │
                    └───────────────┬───────────────────┘
                                    │
                              Flask API (app.py)
                                    │
                           Web Dashboard (UI)


┌────────────────────┐
│    audit_logs      │
├────────────────────┤
│ PK log_id          │
│    user_email      │  ← who accessed
│    role_name       │  ← under what role
│    query_type      │  ← what kind of query
│    accessed_object │  ← which secure view
│    access_timestamp│  ← when
│    company_context │  ← company in scope
└────────────────────┘
```

---

## 4. Detailed Table Definitions

### A. `revenue_transactions` — Raw Financial Table

This is the master ledger. One row = one financial transaction.

```sql
CREATE TABLE finance_schema.revenue_transactions (
    transaction_id  STRING     PRIMARY KEY,
    company_id      STRING     NOT NULL,
    revenue_amount  DOUBLE     NOT NULL,
    cost_amount     DOUBLE     NOT NULL,
    created_at      TIMESTAMP  NOT NULL,
    region          STRING,
    currency        STRING
);
```

**Example data:**

| transaction_id | company_id | revenue_amount | cost_amount | created_at |
|----------------|-----------|----------------|-------------|------------|
| TXN-001 | C001 | 50,000 | 30,000 | 2024-01-15 |
| TXN-002 | C002 | 75,000 | 40,000 | 2024-02-20 |
| TXN-003 | C001 | 60,000 | 35,000 | 2024-04-10 |

---

### B. `revenue_yearly_view` — Aggregation View

Built by grouping `revenue_transactions` by `company_id` and `YEAR(created_at)`.

```sql
CREATE OR REPLACE VIEW finance_schema.revenue_yearly_view AS
SELECT
    company_id,
    YEAR(created_at)                      AS year,
    SUM(revenue_amount)                   AS total_revenue,
    SUM(cost_amount)                      AS total_cost,
    SUM(revenue_amount - cost_amount)     AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY company_id, YEAR(created_at);
```

**Resulting output for the 3 example transactions above:**

| company_id | year | total_revenue | total_cost | total_profit |
|-----------|------|---------------|------------|--------------|
| C001 | 2024 | 110,000 | 65,000 | 45,000 |
| C002 | 2024 | 75,000 | 40,000 | 35,000 |

---

### C. `revenue_quarterly_view` — Quarterly Aggregation

Same as yearly but adds `QUARTER(created_at)`:

```sql
CREATE OR REPLACE VIEW finance_schema.revenue_quarterly_view AS
SELECT
    company_id,
    YEAR(created_at)                      AS year,
    QUARTER(created_at)                   AS quarter,
    SUM(revenue_amount)                   AS total_revenue,
    SUM(cost_amount)                      AS total_cost,
    SUM(revenue_amount - cost_amount)     AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY company_id, YEAR(created_at), QUARTER(created_at);
```

**Resulting output:**

| company_id | year | quarter | total_revenue | total_cost | total_profit |
|-----------|------|---------|---------------|------------|--------------|
| C001 | 2024 | 1 | 50,000 | 30,000 | 20,000 |
| C001 | 2024 | 2 | 60,000 | 35,000 | 25,000 |
| C002 | 2024 | 1 | 75,000 | 40,000 | 35,000 |

---

### D. `governance_schema.users` — Identity Table

```sql
CREATE TABLE governance_schema.users (
    user_id     STRING   PRIMARY KEY,
    email       STRING   NOT NULL,
    role_name   STRING   NOT NULL,   -- 'admin' | 'finance_user' | 'auditor'
    company_id  STRING               -- NULL for admin/auditor; 'C001' for finance_user
);
```

**Example data:**

| user_id | email | role_name | company_id |
|---------|-------|-----------|------------|
| U001 | admin@platform.com | admin | NULL |
| U002 | alpha@company.com | finance_user | C001 |
| U003 | beta@company.com | finance_user | C002 |
| U999 | ganesh.shinde@elliotsystems.com | admin | NULL |

**Rules:**
- `admin` → `company_id = NULL` → sees all companies, sees all columns
- `finance_user` → `company_id = 'C001'` → sees only C001 rows, sees all columns
- `auditor` → `company_id = NULL` → sees all companies, profit column masked to NULL

---

### E. `governance_schema.audit_logs` — Compliance Table

```sql
CREATE TABLE governance_schema.audit_logs (
    log_id            STRING     PRIMARY KEY,
    user_email        STRING     NOT NULL,
    role_name         STRING     NOT NULL,
    query_type        STRING,
    accessed_object   STRING,
    access_timestamp  TIMESTAMP  NOT NULL,
    company_context   STRING
);
```

---

## 5. The Secure View — How It All Connects

The Secure View is the single most important piece of the architecture. It joins financial data with identity data at query time using `current_user()`.

### Full SQL for `secure_revenue_yearly`:

```sql
CREATE OR REPLACE VIEW finance_schema.secure_revenue_yearly AS
SELECT
    v.company_id,
    v.year,
    v.total_revenue,
    v.total_cost,

    -- Column Masking: auditors cannot see profit
    CASE
        WHEN u.role_name = 'auditor' THEN NULL
        ELSE v.total_profit
    END AS total_profit

FROM finance_schema.revenue_yearly_view v

-- The JOIN that connects financial data to identity
JOIN governance_schema.users u ON u.email = current_user()

WHERE
    -- Row-Level Security rules:
    (u.role_name = 'admin')                               -- admin sees all
    OR (u.role_name = 'auditor')                           -- auditor sees all (but profit masked above)
    OR (u.role_name = 'finance_user' AND v.company_id = u.company_id)  -- finance sees only own company
;
```

---

## 6. Step-by-Step Execution Walkthrough

### Scenario A: Finance User from C001

```
Step 1 → User's Databricks token sends query to secure_revenue_yearly
Step 2 → Databricks calls current_user() → returns 'alpha@company.com'
Step 3 → JOIN finds user row: { role: 'finance_user', company_id: 'C001' }
Step 4 → WHERE clause:
         - role = 'admin'? NO
         - role = 'auditor'? NO
         - role = 'finance_user' AND company_id matches? YES only for C001 rows
Step 5 → Only C001 rows pass through
Step 6 → CASE: role = 'auditor'? NO → actual profit values included
Step 7 → Result: C001 data with real profit numbers
```

### Scenario B: Auditor

```
Step 1 → Auditor token queries secure_revenue_yearly
Step 2 → current_user() → 'ganesh.shinde@elliotsystems.com' (when role was auditor)
Step 3 → JOIN finds: { role: 'auditor', company_id: NULL }
Step 4 → WHERE: role = 'auditor'? YES → ALL rows from all companies pass
Step 5 → CASE: role = 'auditor'? YES → total_profit = NULL for every row
Step 6 → Result: all companies visible, but profit column shows "—" (NULL)
```

### Scenario C: Admin

```
Step 1 → Admin token queries secure_revenue_yearly
Step 2 → current_user() → 'admin@platform.com'
Step 3 → JOIN finds: { role: 'admin', company_id: NULL }
Step 4 → WHERE: role = 'admin'? YES → ALL rows from all companies pass
Step 5 → CASE: role = 'auditor'? NO → actual profit values included
Step 6 → Result: all companies, all columns, full data
```

---

## 7. Data Flow Summary

```
revenue_transactions (raw rows)
    │
    │ GROUP BY company_id + YEAR/QUARTER
    │
    ├──► revenue_yearly_view (yearly totals)
    │         │
    │         │ JOIN users ON email = current_user()
    │         │ + WHERE (role checks) + CASE (column masking)
    │         │
    │         └──► secure_revenue_yearly   ← Flask API queries this
    │
    └──► revenue_quarterly_view (quarterly totals)
              │
              │ JOIN users ON email = current_user()
              │ + WHERE (role checks) + CASE (column masking)
              │
              └──► secure_revenue_quarterly  ← Flask API queries this
```

---

## 8. Key Takeaways

1. **The `users` table is the key to everything.** If someone's email and role are wrong in this table, they get wrong access. The bug we fixed (total_profit showing NULL for admin) was because the `users` table had the wrong role for the Databricks token owner.

2. **`current_user()` is the bridge.** It returns the email of whoever owns the Databricks access token. This email is looked up in the `users` table to determine the role.

3. **The Secure View is not optional.** Raw tables and aggregation views have zero granted permissions. The ONLY path to data is through the secure views.

4. **Security happens in SQL, not in Python code.** The Flask API does not filter rows or mask columns. The database does it automatically.

---

*Next: See `04_governance_and_security.md` for a deep dive into the role design and enforcement rules.*
