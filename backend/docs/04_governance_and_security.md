# 🛡️ Governance & Security (RBAC Enforcement)

---

## 1. What This Document Covers

This document explains the **complete security model** of the Governed Data Platform. It covers:

- Why security is at the database level (not just the API)
- The three roles and what each one can do
- Row-Level Security (RLS) — which rows a user can see
- Column-Level Masking (CLS) — which columns are hidden
- Multi-tenancy — how companies are isolated from each other
- Defense layers — what happens if the API or AI is compromised
- Common mistakes this design avoids

---

## 2. Why Security Lives in the Database

### The Common (Bad) Pattern

Most applications do security like this:

```
Database → returns ALL data to backend → backend code filters by role → sends filtered result to user
```

**Problems:**
- The backend has a "god mode" connection to the database.
- If the backend is hacked, all data is exposed.
- A developer could accidentally remove a filter and expose data.
- AI-generated queries bypass code-level filters entirely.
- There is no database-level proof of what data was actually returned.

### Our Pattern (Strong)

```
Database → Secure View checks role via current_user() → returns ONLY authorized data → backend passes it through
```

**Advantages:**
- The backend never sees data the user shouldn't see.
- Even if the backend is hacked, the database enforces the rules.
- AI-generated queries hit the same Secure Views — same rules apply.
- The database is the final enforcement point — nothing can bypass it.

---

## 3. The Three Roles

The platform defines exactly three roles. These are stored in the `governance_schema.users` table in the `role_name` column.

### Role 1: Admin

| Property | Value |
|----------|-------|
| **See all companies?** | ✅ Yes |
| **See profit data?** | ✅ Yes |
| **company_id in users table** | `NULL` (not restricted) |
| **Use case** | Platform administrators who manage the entire system |

An admin sees **everything**. All companies, all columns, all data.

### Role 2: Finance User

| Property | Value |
|----------|-------|
| **See all companies?** | ❌ Only their own company |
| **See profit data?** | ✅ Yes (for their company) |
| **company_id in users table** | e.g. `'C001'` |
| **Use case** | Company-specific financial analysts |

A finance user is **restricted to their assigned company**. They can see all financial metrics (including profit) but ONLY for their own company. They cannot see any other company's data.

### Role 3: Auditor

| Property | Value |
|----------|-------|
| **See all companies?** | ✅ Yes |
| **See profit data?** | ❌ No — shows as NULL |
| **company_id in users table** | `NULL` (not restricted) |
| **Use case** | Compliance officers who need to review patterns across all companies but should not see exact profit numbers |

An auditor can see rows from **all companies** (they need to audit across the platform), but the **`total_profit` column is masked to `NULL`**. They can see revenue and cost, but not profit.

### Role Comparison Table

| Capability | Admin | Finance User | Auditor |
|-----------|-------|-------------|---------|
| See all companies | ✅ | ❌ Own only | ✅ |
| See total_revenue | ✅ | ✅ | ✅ |
| See total_cost | ✅ | ✅ | ✅ |
| See total_profit | ✅ | ✅ | ❌ NULL |
| Query yearly data | ✅ | ✅ (own company) | ✅ |
| Query quarterly data | ✅ | ✅ (own company) | ✅ |

---

## 4. Row-Level Security (RLS)

### What It Does

Row-Level Security controls **which rows from the database a user can see**. It does not hide columns — it hides entire rows.

### How It Works

Inside the Secure Views, there is a `WHERE` clause that checks the user's role:

```sql
WHERE
    (u.role_name = 'admin')
    OR (u.role_name = 'auditor')
    OR (
        u.role_name = 'finance_user'
        AND v.company_id = u.company_id
    );
```

### What Happens Per Role

**Admin:** `u.role_name = 'admin'` is `TRUE` → all rows pass → sees everything.

**Auditor:** `u.role_name = 'auditor'` is `TRUE` → all rows pass → sees all companies.

**Finance User (C001):** Only the third condition applies:
- `u.role_name = 'finance_user'` is `TRUE`
- `AND v.company_id = u.company_id` → only rows where `company_id = 'C001'`
- Result: sees only C001 rows. C002, C003, C004 rows are completely invisible.

### Example

Database has these rows:

| company_id | year | total_revenue |
|-----------|------|---------------|
| C001 | 2024 | 700,000 |
| C002 | 2024 | 300,000 |
| C003 | 2024 | 800,000 |
| C004 | 2024 | 600,000 |

**What admin sees:** All 4 rows.
**What auditor sees:** All 4 rows.
**What finance_user (C001) sees:** Only the C001 row (1 row).
**What finance_user (C002) sees:** Only the C002 row (1 row).

The other rows don't just appear empty — they literally do not exist in the query result. The database never returns them.

---

## 5. Column-Level Masking (CLS)

### What It Does

Column-Level Masking controls **which columns a user can see values for**. The column still appears in the result set, but its value is replaced with `NULL`.

### How It Works

Inside the Secure Views, a `CASE/WHEN` expression replaces the `total_profit` value:

```sql
CASE
    WHEN u.role_name = 'auditor' THEN NULL
    ELSE v.total_profit
END AS total_profit
```

### What Happens Per Role

**Admin:** `role_name = 'auditor'` is `FALSE` → `ELSE v.total_profit` → actual profit value shown.

**Finance User:** Same as admin → actual profit value shown (for their company).

**Auditor:** `role_name = 'auditor'` is `TRUE` → `NULL` → profit column shows `NULL` for every row.

### Example

Same 4 rows. Auditor queries:

| company_id | year | total_revenue | total_cost | total_profit |
|-----------|------|---------------|------------|--------------|
| C001 | 2024 | 700,000 | 400,000 | NULL |
| C002 | 2024 | 300,000 | 150,000 | NULL |
| C003 | 2024 | 800,000 | 500,000 | NULL |
| C004 | 2024 | 600,000 | 400,000 | NULL |

The auditor can see revenue and cost for all companies — they just cannot see the exact profit figures.

In the dashboard UI, `NULL` values display as "—" (a dash).

---

## 6. Multi-Tenancy (Company Isolation)

### What Multi-Tenancy Means

Multi-tenancy means **multiple companies share the same database**, but each company's data is isolated from the others.

### How It Works

The isolation key is `company_id`.

In the `users` table:
- `finance_user` users have a `company_id` like `'C001'`.
- The Secure View checks: `v.company_id = u.company_id`.
- If the user belongs to C001, only C001 rows are returned.
- C002's data is not filtered out by the API — it is filtered out by the database.

### Why This Is Better Than API Filtering

If multi-tenancy was handled in the Flask API:
```python
# BAD: API gets all data and filters
all_data = run_query("SELECT * FROM revenue_yearly")
user_data = [row for row in all_data if row.company_id == user.company_id]
```

Problems with this approach:
- All company data is loaded into memory.
- A bug in the filter logic exposes all companies.
- The database returns more data than needed.

With database-level enforcement:
```sql
-- GOOD: Database only returns what this user is allowed to see
SELECT * FROM secure_revenue_yearly;
-- Internally: WHERE v.company_id = u.company_id (for finance_user)
```

The Flask API runs the exact same query for every user. The database returns different results based on who is asking. The API code does not need to know about company isolation at all.

---

## 7. The `current_user()` Bridge

### How Databricks Identifies the User

When the Flask API connects to Databricks using the access token from `.env`:

```python
# From db.py
def get_connection():
    return sql.connect(
        server_hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME"),
        http_path       = os.getenv("DATABRICKS_HTTP_PATH"),
        access_token    = os.getenv("DATABRICKS_TOKEN"),   # ← This token determines current_user()
    )
```

The `access_token` belongs to a specific Databricks account. When the secure view calls `current_user()`, Databricks returns the email associated with that token.

### Important Implication

The role displayed in the UI dropdown (Admin / Finance User / Auditor) is **for UI testing purposes**. The actual security enforcement depends on what email the Databricks token resolves to, and what role that email has in the `governance_schema.users` table.

This is exactly why we saw the "total_profit is NULL for admin" bug earlier — the Databricks token resolved to `ganesh.shinde@elliotsystems.com`, which had role `auditor` in the database. Changing the UI dropdown to "Admin" did nothing — the database still enforced auditor rules because that was the role stored for that email.

We fixed it by updating the `users` table:
```sql
UPDATE governance_schema.users 
SET role_name = 'admin' 
WHERE email = 'ganesh.shinde@elliotsystems.com'
```

---

## 8. Permission Lockdown (GRANT / REVOKE)

To ensure nobody bypasses the Secure Views, we apply strict permission rules:

```sql
-- Remove all access to raw data
REVOKE ALL PRIVILEGES ON SCHEMA finance_schema FROM `users`;
REVOKE ALL PRIVILEGES ON SCHEMA governance_schema FROM `users`;

-- Grant access ONLY to the two secure views
GRANT SELECT ON VIEW finance_schema.secure_revenue_yearly TO `users`;
GRANT SELECT ON VIEW finance_schema.secure_revenue_quarterly TO `users`;
```

This means:
- ❌ Cannot query `revenue_transactions` directly
- ❌ Cannot query `revenue_yearly_view` or `revenue_quarterly_view` directly
- ❌ Cannot query `governance_schema.users` or `audit_logs` directly
- ✅ Can ONLY query `secure_revenue_yearly` and `secure_revenue_quarterly`

---

## 9. Defense Against Application Compromise

The architecture is designed to remain secure even if the application tier is compromised.

| Threat | Defense |
|--------|---------|
| Backend hacked → attacker tries to query raw tables | Permission denied — only secure views are accessible |
| AI generates a `DROP TABLE` query | SQL Firewall blocks it (Layer 1: only SELECT allowed) |
| AI tries to query `governance_schema.users` | SQL Firewall blocks it (Layer 4: blocked schema) |
| AI generates `SELECT * FROM secure_revenue_yearly` | Works — but Secure View still enforces RLS and CLS based on token |
| Someone manually changes the `X-User-Role` header | Does nothing — database uses `current_user()`, not HTTP headers |
| SQL injection via user input | Predefined queries never interpolate user input into SQL |

---

## 10. Common Mistakes This Design Avoids

| Mistake | How We Avoid It |
|---------|----------------|
| Applying filtering only in backend code | Filtering is in the database Secure Views |
| Allowing direct access to raw tables | `REVOKE ALL PRIVILEGES` applied |
| Not masking sensitive columns | `CASE/WHEN` masks `total_profit` for auditors |
| Not logging data access | `audit_logs` table records every access |
| Mixing business data and governance data | Separate schemas: `finance_schema` vs `governance_schema` |
| Forgetting role validation | `current_user()` → `users` table lookup happens automatically in every query |
| Trusting AI output | 5-layer SQL firewall + post-execution governance check |

---

## 11. How to Present This to a Team

> "We designed a layered governed data architecture. Raw financial transactions are stored in a base table. Business aggregation views calculate yearly and quarterly metrics. A governance schema manages users and roles. Secure views enforce row-level and column-level security directly in the database. All access is audit-logged for compliance. Even if the API is compromised, the database itself prevents unauthorized data access."

---

*Next: See `05_api_and_ui_layer.md` for the Flask API and dashboard architecture.*
