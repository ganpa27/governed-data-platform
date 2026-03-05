-- ==============================================================================
-- STAGE 1 GOVERNANCE ARCHITECTURE SETUP
-- Target Environment: Databricks Unity Catalog
-- Purpose: Builds the secure schema, raw tables, user tables, and secure views
--          that enforce the Stage 1 RBAC Governance Rulebook.
-- ==============================================================================

-- 1. CREATE CATALOG & SCHEMAS
-- ------------------------------------------------------------------------------
CREATE CATALOG IF NOT EXISTS governed_platform_catalog;

USE CATALOG governed_platform_catalog;

-- Finance Schema for financial data and views
CREATE SCHEMA IF NOT EXISTS finance_schema;

-- Governance Schema for security configuration (users, audit)
CREATE SCHEMA IF NOT EXISTS governance_schema;

-- 2. CREATE GOVERNANCE USER TABLE
-- ------------------------------------------------------------------------------
-- This defines who has what role and which company they belong to.
CREATE TABLE IF NOT EXISTS governance_schema.users (
    user_id STRING PRIMARY KEY,
    email STRING NOT NULL,
    role_name STRING NOT NULL, -- 'admin' | 'finance_user' | 'auditor'
    company_id STRING -- NULL for admin/auditor, specific ID for finance
);

-- Example Insert:
-- INSERT INTO governance_schema.users VALUES
--  ('U001', 'admin@elliot.com', 'admin', NULL),
--  ('U002', 'finance1@elliot.com', 'finance_user', 'C001'),
--  ('U003', 'auditor@elliot.com', 'auditor', NULL);

-- 3. CREATE RAW FINANCIAL TRANSACTIONS TABLE (PROTECTED)
-- ------------------------------------------------------------------------------
-- Raw data. NO USER HAS DIRECT ACCESS TO THIS TABLE.
CREATE TABLE IF NOT EXISTS finance_schema.revenue_transactions (
    transaction_id STRING PRIMARY KEY,
    company_id STRING NOT NULL,
    revenue_amount DOUBLE NOT NULL,
    cost_amount DOUBLE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    region STRING,
    currency STRING
);

-- 4. CREATE SYSTEM AUDIT LOG (PROTECTED)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS governance_schema.audit_logs (
    log_id STRING PRIMARY KEY,
    user_email STRING NOT NULL,
    role_name STRING NOT NULL,
    query_type STRING,
    accessed_object STRING,
    access_timestamp TIMESTAMP NOT NULL,
    company_context STRING
);

-- 5. CREATE BASE AGGREGATION VIEWS (NOT DIRECTLY EXPOSED)
-- ------------------------------------------------------------------------------
-- These simply perform the math without security logic.

CREATE OR REPLACE VIEW finance_schema.revenue_yearly_view AS
SELECT
    company_id,
    YEAR(created_at) AS year,
    SUM(revenue_amount) AS total_revenue,
    SUM(cost_amount) AS total_cost,
    SUM(revenue_amount - cost_amount) AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY
    company_id,
    YEAR(created_at);

CREATE OR REPLACE VIEW finance_schema.revenue_quarterly_view AS
SELECT
    company_id,
    YEAR(created_at) AS year,
    QUARTER(created_at) AS quarter,
    SUM(revenue_amount) AS total_revenue,
    SUM(cost_amount) AS total_cost,
    SUM(revenue_amount - cost_amount) AS total_profit
FROM finance_schema.revenue_transactions
GROUP BY
    company_id,
    YEAR(created_at),
    QUARTER(created_at);

-- 6. CREATE SECURE VIEWS 🔒 (THE ONLY EXPOSED OBJECTS)
-- ------------------------------------------------------------------------------
-- These views embed the row-level security and column masking logic.
-- They rely on mapping `current_user()` to the `governance_schema.users` table.

-- A) Secure Yearly Revenue
CREATE OR REPLACE VIEW finance_schema.secure_revenue_yearly AS
SELECT
    v.company_id,
    v.year,
    v.total_revenue,
    v.total_cost,
    -- COLUMN MASKING RULE:
    CASE
        WHEN u.role_name = 'auditor' THEN NULL
        ELSE v.total_profit
    END AS total_profit
FROM finance_schema.revenue_yearly_view v

-- MULTI-TENANT & RLS LOGIC via JOIN:
-- current_user() grabs the Databricks login email
JOIN governance_schema.users u ON u.email = current_user()
WHERE
    -- ROW ACCESS RULE:
    (u.role_name = 'admin')
    OR (u.role_name = 'auditor')
    OR (
        u.role_name = 'finance_user'
        AND v.company_id = u.company_id
    );

-- B) Secure Quarterly Revenue
CREATE OR REPLACE VIEW finance_schema.secure_revenue_quarterly AS
SELECT
    v.company_id,
    v.year,
    v.quarter,
    v.total_revenue,
    v.total_cost,
    -- COLUMN MASKING RULE:
    CASE
        WHEN u.role_name = 'auditor' THEN NULL
        ELSE v.total_profit
    END AS total_profit
FROM finance_schema.revenue_quarterly_view v
    JOIN governance_schema.users u ON u.email = current_user()
WHERE (u.role_name = 'admin')
    OR (u.role_name = 'auditor')
    OR (
        u.role_name = 'finance_user'
        AND v.company_id = u.company_id
    );

-- 7. APPLY STRICT GRANTS (FINAL LOCKDOWN)
-- ------------------------------------------------------------------------------
-- Revoke all access to the raw schema
REVOKE ALL PRIVILEGES ON SCHEMA finance_schema FROM `users`;

REVOKE ALL PRIVILEGES ON SCHEMA governance_schema FROM `users`;

-- Grant read access ONLY on the SECURE views
GRANT SELECT ON VIEW finance_schema.secure_revenue_yearly TO `users`;

GRANT
SELECT ON VIEW finance_schema.secure_revenue_quarterly TO `users`;