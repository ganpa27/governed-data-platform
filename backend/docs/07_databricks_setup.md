# ☁️ Databricks Setup & Configuration

---

## 1. What This Document Covers

This document explains everything about the Databricks environment — how to set it up from scratch, what each component does, and how the application connects to it.

---

## 2. What Is Databricks?

Databricks is a cloud-based data and AI platform built on top of Apache Spark. In this project, we use Databricks specifically for:

- **Unity Catalog**: A governance layer that lets us organize data into catalogs and schemas.
- **SQL Warehouses**: compute resources that execute our SQL queries.
- **Access Control**: `current_user()` function that lets secure views identify who is querying.
- **Token-based Authentication**: a personal access token (PAT) that our Flask API uses to connect.

We do NOT use Databricks for:
- Machine learning training (that's separate)
- Data engineering pipelines
- Spark cluster management

We use it purely as a **governed SQL database** with built-in identity awareness.

---

## 3. Unity Catalog Structure

Unity Catalog organizes data in a 3-level hierarchy:

```
Catalog → Schema → Table / View
```

Our structure:

```
governed_platform_catalog              ← Catalog (top level)
├── finance_schema                     ← Schema for financial data
│   ├── revenue_transactions           ← Table: raw financial events
│   ├── revenue_yearly_view            ← View: yearly aggregation
│   ├── revenue_quarterly_view         ← View: quarterly aggregation
│   ├── secure_revenue_yearly          ← Secure View: role-filtered yearly output
│   └── secure_revenue_quarterly       ← Secure View: role-filtered quarterly output
│
└── governance_schema                  ← Schema for security
    ├── users                          ← Table: user-role mappings
    └── audit_logs                     ← Table: access compliance records
```

---

## 4. Setting Up the Database (Step by Step)

The entire database schema is defined in `stage1_governance_architecture.sql`. Here is how to execute it:

### Step 1: Create the Catalog

```sql
CREATE CATALOG IF NOT EXISTS governed_platform_catalog;
USE CATALOG governed_platform_catalog;
```

### Step 2: Create the Schemas

```sql
CREATE SCHEMA IF NOT EXISTS finance_schema;
CREATE SCHEMA IF NOT EXISTS governance_schema;
```

### Step 3: Create the Users Table

```sql
CREATE TABLE IF NOT EXISTS governance_schema.users (
    user_id    STRING PRIMARY KEY,
    email      STRING NOT NULL,
    role_name  STRING NOT NULL,
    company_id STRING
);
```

### Step 4: Insert Users

```sql
INSERT INTO governance_schema.users VALUES
  ('U001', 'admin@platform.com', 'admin', NULL),
  ('U002', 'alpha@company.com', 'finance_user', 'C001'),
  ('U003', 'beta@company.com', 'finance_user', 'C002'),
  ('U999', 'ganesh.shinde@elliotsystems.com', 'admin', NULL);
```

**Important**: The email for `U999` must match the email of the Databricks account that owns the access token used by the Flask API. If this is wrong, the secure views will not return the correct data.

### Step 5: Create the Raw Transactions Table

```sql
CREATE TABLE IF NOT EXISTS finance_schema.revenue_transactions (
    transaction_id STRING PRIMARY KEY,
    company_id     STRING NOT NULL,
    revenue_amount DOUBLE NOT NULL,
    cost_amount    DOUBLE NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    region         STRING,
    currency       STRING
);
```

### Step 6: Create the Audit Logs Table

```sql
CREATE TABLE IF NOT EXISTS governance_schema.audit_logs (
    log_id           STRING PRIMARY KEY,
    user_email       STRING NOT NULL,
    role_name        STRING NOT NULL,
    query_type       STRING,
    accessed_object  STRING,
    access_timestamp TIMESTAMP NOT NULL,
    company_context  STRING
);
```

### Step 7: Create Aggregation Views

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

### Step 8: Create Secure Views

```sql
-- Yearly
CREATE OR REPLACE VIEW finance_schema.secure_revenue_yearly AS
SELECT
    v.company_id, v.year, v.total_revenue, v.total_cost,
    CASE WHEN u.role_name = 'auditor' THEN NULL ELSE v.total_profit END AS total_profit
FROM finance_schema.revenue_yearly_view v
JOIN governance_schema.users u ON u.email = current_user()
WHERE (u.role_name = 'admin') OR (u.role_name = 'auditor')
   OR (u.role_name = 'finance_user' AND v.company_id = u.company_id);

-- Quarterly
CREATE OR REPLACE VIEW finance_schema.secure_revenue_quarterly AS
SELECT
    v.company_id, v.year, v.quarter, v.total_revenue, v.total_cost,
    CASE WHEN u.role_name = 'auditor' THEN NULL ELSE v.total_profit END AS total_profit
FROM finance_schema.revenue_quarterly_view v
JOIN governance_schema.users u ON u.email = current_user()
WHERE (u.role_name = 'admin') OR (u.role_name = 'auditor')
   OR (u.role_name = 'finance_user' AND v.company_id = u.company_id);
```

### Step 9: Apply Permission Lockdown

```sql
REVOKE ALL PRIVILEGES ON SCHEMA finance_schema FROM `users`;
REVOKE ALL PRIVILEGES ON SCHEMA governance_schema FROM `users`;
GRANT SELECT ON VIEW finance_schema.secure_revenue_yearly TO `users`;
GRANT SELECT ON VIEW finance_schema.secure_revenue_quarterly TO `users`;
```

---

## 5. Obtaining a Databricks Access Token

1. Log in to your Databricks workspace.
2. Click on your profile icon (top-right corner).
3. Go to **User Settings** → **Developer** → **Access Tokens**.
4. Click **Generate New Token**.
5. Give it a description (e.g., "Governed Platform API").
6. Set an expiration (or no expiration for development).
7. Copy the token — it starts with `dapi...`.

This token goes into the `.env` file:

```
DATABRICKS_TOKEN=dapi...your_token_here...
```

---

## 6. Getting Connection Details

### Server Hostname
Found in the Databricks workspace URL:
```
https://adb-1234567890123456.7.azuredatabricks.net
```
The hostname is: `adb-1234567890123456.7.azuredatabricks.net`

### HTTP Path
Found in the SQL Warehouse settings:
1. Go to **SQL Warehouses** in Databricks.
2. Click on your warehouse.
3. Go to **Connection Details** tab.
4. Copy the **HTTP Path** — it looks like: `/sql/1.0/warehouses/abc123def456`

---

## 7. The `.env` File

The Flask API reads all Databricks credentials from `.env`:

```env
# Databricks Connection
DATABRICKS_SERVER_HOSTNAME=adb-1234567890123456.7.azuredatabricks.net
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your_warehouse_id
DATABRICKS_TOKEN=dapi_your_personal_access_token

# Groq AI (optional — needed for AI-powered queries)
GROQ_API_KEY=gsk_your_groq_api_key

# AI Configuration
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_BASE_URL=https://api.groq.com/openai/v1
AI_MAX_TOKENS=500
AI_TEMPERATURE=0.1
```

---

## 8. How `current_user()` Works

When the Flask API connects to Databricks using the access token:

```python
# db.py
sql.connect(
    server_hostname = "adb-123...",
    http_path       = "/sql/1.0/warehouses/...",
    access_token    = "dapi_...",
)
```

Databricks associates this connection with the account that owns the token. When any SQL query calls `current_user()`, it returns the email of that account.

For example:
- If the token belongs to `ganesh.shinde@elliotsystems.com`
- Then `current_user()` returns `'ganesh.shinde@elliotsystems.com'`
- The secure view JOINs this email to the `users` table to find the role

### Important: Single Token = Single Identity

Currently, the Flask API uses a single Databricks token. This means:
- All queries from the dashboard execute as the same Databricks user.
- The role is determined by the row in `governance_schema.users` matching that email.
- The UI role dropdown does NOT change the Databricks identity.

For a production system, each user would have their own Databricks token, and `current_user()` would return their individual email.

---

## 9. Verifying Your Setup

After completing the setup, verify everything works:

### Check 1: Verify the current user

```sql
SELECT current_user();
-- Should return your Databricks email
```

### Check 2: Verify users table

```sql
SELECT * FROM governed_platform_catalog.governance_schema.users;
-- Should show all registered users with their roles
```

### Check 3: Test secure view

```sql
SELECT * FROM governed_platform_catalog.finance_schema.secure_revenue_yearly LIMIT 5;
-- Should return data filtered by your role
-- Check if total_profit is NULL (auditor) or has values (admin/finance)
```

### Check 4: Verify your role assignment

```sql
SELECT email, role_name FROM governed_platform_catalog.governance_schema.users 
WHERE email = current_user();
-- Confirm this shows the role you expect
```

---

## 10. Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `total_profit` shows NULL for admin | Your email has wrong role in `users` table | `UPDATE governance_schema.users SET role_name = 'admin' WHERE email = 'your@email.com'` |
| Connection error from Flask | Wrong hostname or HTTP path | Double-check `.env` values against Databricks workspace |
| TLS certificate error on macOS | Missing CA certificates | The `certifi` library in `db.py` fixes this |
| Empty results from secure view | Your email is not in the `users` table | Insert a row with your email and desired role |
| "No module named databricks" | Virtual environment not activated | Run `source venv/bin/activate` first |

---

*Next: See `08_data_flow_and_summary.md` for the complete end-to-end data flow diagram.*
