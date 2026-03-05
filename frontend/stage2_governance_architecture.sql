-- ==============================================================================
-- STAGE 2: ENHANCED GOVERNANCE ARCHITECTURE
-- Target: Databricks Unity Catalog
-- Purpose: Production-ready schema with named companies, 5 distinct roles,
--          named users, and realistic multi-year financial data.
-- ==============================================================================

-- 1. CREATE CATALOG & SCHEMAS
-- ------------------------------------------------------------------------------
CREATE CATALOG IF NOT EXISTS governed_platform_catalog;

USE CATALOG governed_platform_catalog;

CREATE SCHEMA IF NOT EXISTS finance_schema;

CREATE SCHEMA IF NOT EXISTS governance_schema;

-- ==============================================================================
-- 2. COMPANIES TABLE (NEW) — named, with industry & region
-- ==============================================================================
CREATE TABLE IF NOT EXISTS finance_schema.companies (
    company_id STRING PRIMARY KEY,
    company_name STRING NOT NULL,
    industry STRING,
    region STRING,
    created_at TIMESTAMP DEFAULT current_timestamp()
);

-- Clear and reload
DELETE FROM finance_schema.companies;

INSERT INTO
    finance_schema.companies
VALUES (
        'C001',
        'Elliot Systems',
        'Technology',
        'Mumbai',
        current_timestamp()
    ),
    (
        'C002',
        'TechNova Solutions',
        'IT Services',
        'Bangalore',
        current_timestamp()
    ),
    (
        'C003',
        'GreenField Industries',
        'Manufacturing',
        'Pune',
        current_timestamp()
    ),
    (
        'C004',
        'Meridian Corp',
        'Finance',
        'Delhi',
        current_timestamp()
    ),
    (
        'C005',
        'Atlas Dynamics',
        'Automotive',
        'Chennai',
        current_timestamp()
    );

-- ==============================================================================
-- 3. GOVERNANCE USER TABLE — 5 roles, named users
-- ==============================================================================
-- Roles:
--   admin        → Full access: all rows, all columns
--   manager      → Full access: all rows, all columns (senior leadership)
--   finance_user → Own company only, all columns
--   auditor      → All rows, profit MASKED
--   viewer       → All rows, cost + profit MASKED

CREATE TABLE IF NOT EXISTS governance_schema.users (
    user_id STRING PRIMARY KEY,
    full_name STRING NOT NULL,
    email STRING NOT NULL,
    role_name STRING NOT NULL,
    company_id STRING,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT current_timestamp()
);

-- Clear and reload
DELETE FROM governance_schema.users;

INSERT INTO
    governance_schema.users
VALUES (
        'U001',
        'Ganesh Shinde',
        'ganesh.shinde@elliotsystems.com',
        'admin',
        NULL,
        TRUE,
        current_timestamp()
    ),
    (
        'U002',
        'Priya Sharma',
        'priya.sharma@elliotsystems.com',
        'manager',
        NULL,
        TRUE,
        current_timestamp()
    ),
    (
        'U003',
        'Rahul Mehta',
        'rahul.mehta@elliotsystems.com',
        'finance_user',
        'C001',
        TRUE,
        current_timestamp()
    ),
    (
        'U004',
        'Anita Desai',
        'anita.desai@technova.com',
        'finance_user',
        'C002',
        TRUE,
        current_timestamp()
    ),
    (
        'U005',
        'Vikram Joshi',
        'vikram.joshi@compliance.com',
        'auditor',
        NULL,
        TRUE,
        current_timestamp()
    ),
    (
        'U006',
        'Sara Khan',
        'sara.khan@investor.com',
        'viewer',
        NULL,
        TRUE,
        current_timestamp()
    );

-- ==============================================================================
-- 4. RAW FINANCIAL TRANSACTIONS (PROTECTED — no direct access)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS finance_schema.revenue_transactions (
    transaction_id STRING PRIMARY KEY,
    company_id STRING NOT NULL,
    revenue_amount DOUBLE NOT NULL,
    cost_amount DOUBLE NOT NULL,
    revenue_type STRING,
    region STRING,
    currency STRING DEFAULT 'INR',
    created_at TIMESTAMP NOT NULL
);

-- Clear and reload with rich multi-year data
DELETE FROM finance_schema.revenue_transactions;

INSERT INTO
    finance_schema.revenue_transactions
VALUES
    -- ──────────────── C001 — Elliot Systems (Technology, Mumbai) ─────────────────
    -- 2023
    (
        'T001',
        'C001',
        250000,
        140000,
        'Product',
        'Mumbai',
        'INR',
        '2023-02-15'
    ),
    (
        'T002',
        'C001',
        180000,
        95000,
        'Service',
        'Mumbai',
        'INR',
        '2023-05-22'
    ),
    (
        'T003',
        'C001',
        320000,
        175000,
        'Product',
        'Pune',
        'INR',
        '2023-08-10'
    ),
    (
        'T004',
        'C001',
        150000,
        80000,
        'Subscription',
        'Mumbai',
        'INR',
        '2023-11-28'
    ),
    -- 2024
    (
        'T005',
        'C001',
        350000,
        190000,
        'Product',
        'Mumbai',
        'INR',
        '2024-01-18'
    ),
    (
        'T006',
        'C001',
        200000,
        110000,
        'Service',
        'Pune',
        'INR',
        '2024-04-25'
    ),
    (
        'T007',
        'C001',
        280000,
        155000,
        'Subscription',
        'Mumbai',
        'INR',
        '2024-07-12'
    ),
    (
        'T008',
        'C001',
        420000,
        230000,
        'Product',
        'Delhi',
        'INR',
        '2024-10-05'
    ),

-- ──────────────── C002 — TechNova Solutions (IT Services, Bangalore) ────────
-- 2023
(
    'T009',
    'C002',
    180000,
    100000,
    'Service',
    'Bangalore',
    'INR',
    '2023-03-10'
),
(
    'T010',
    'C002',
    95000,
    55000,
    'Subscription',
    'Bangalore',
    'INR',
    '2023-06-18'
),
(
    'T011',
    'C002',
    210000,
    120000,
    'Service',
    'Chennai',
    'INR',
    '2023-09-22'
),
(
    'T012',
    'C002',
    130000,
    70000,
    'Product',
    'Bangalore',
    'INR',
    '2023-12-05'
),
-- 2024
(
    'T013',
    'C002',
    220000,
    115000,
    'Service',
    'Bangalore',
    'INR',
    '2024-02-14'
),
(
    'T014',
    'C002',
    155000,
    85000,
    'Subscription',
    'Chennai',
    'INR',
    '2024-05-20'
),
(
    'T015',
    'C002',
    280000,
    150000,
    'Service',
    'Bangalore',
    'INR',
    '2024-08-08'
),
(
    'T016',
    'C002',
    170000,
    90000,
    'Product',
    'Hyderabad',
    'INR',
    '2024-11-15'
),

-- ──────────────── C003 — GreenField Industries (Manufacturing, Pune) ────────
-- 2023
(
    'T017',
    'C003',
    400000,
    260000,
    'Product',
    'Pune',
    'INR',
    '2023-01-20'
),
(
    'T018',
    'C003',
    350000,
    230000,
    'Product',
    'Mumbai',
    'INR',
    '2023-04-15'
),
(
    'T019',
    'C003',
    280000,
    190000,
    'Product',
    'Delhi',
    'INR',
    '2023-07-25'
),
(
    'T020',
    'C003',
    310000,
    200000,
    'Service',
    'Pune',
    'INR',
    '2023-10-30'
),
-- 2024
(
    'T021',
    'C003',
    450000,
    280000,
    'Product',
    'Pune',
    'INR',
    '2024-01-12'
),
(
    'T022',
    'C003',
    380000,
    245000,
    'Product',
    'Mumbai',
    'INR',
    '2024-04-18'
),
(
    'T023',
    'C003',
    520000,
    310000,
    'Product',
    'Chennai',
    'INR',
    '2024-07-22'
),
(
    'T024',
    'C003',
    290000,
    180000,
    'Service',
    'Pune',
    'INR',
    '2024-10-28'
),

-- ──────────────── C004 — Meridian Corp (Finance, Delhi) ─────────────────────
-- 2023
(
    'T025',
    'C004',
    190000,
    120000,
    'Service',
    'Delhi',
    'INR',
    '2023-02-28'
),
(
    'T026',
    'C004',
    160000,
    100000,
    'Subscription',
    'Mumbai',
    'INR',
    '2023-05-10'
),
(
    'T027',
    'C004',
    220000,
    140000,
    'Service',
    'Delhi',
    'INR',
    '2023-08-18'
),
(
    'T028',
    'C004',
    175000,
    110000,
    'Product',
    'Bangalore',
    'INR',
    '2023-11-22'
),
-- 2024
(
    'T029',
    'C004',
    240000,
    155000,
    'Service',
    'Delhi',
    'INR',
    '2024-03-08'
),
(
    'T030',
    'C004',
    195000,
    125000,
    'Subscription',
    'Mumbai',
    'INR',
    '2024-06-15'
),
(
    'T031',
    'C004',
    310000,
    195000,
    'Service',
    'Delhi',
    'INR',
    '2024-08-25'
),
(
    'T032',
    'C004',
    180000,
    115000,
    'Product',
    'Pune',
    'INR',
    '2024-12-01'
),

-- ──────────────── C005 — Atlas Dynamics (Automotive, Chennai)  ──(NEW!)──────
-- 2023
(
    'T033',
    'C005',
    500000,
    350000,
    'Product',
    'Chennai',
    'INR',
    '2023-03-05'
),
(
    'T034',
    'C005',
    420000,
    290000,
    'Product',
    'Bangalore',
    'INR',
    '2023-06-22'
),
(
    'T035',
    'C005',
    380000,
    250000,
    'Service',
    'Chennai',
    'INR',
    '2023-09-15'
),
(
    'T036',
    'C005',
    550000,
    370000,
    'Product',
    'Mumbai',
    'INR',
    '2023-12-18'
),
-- 2024
(
    'T037',
    'C005',
    600000,
    400000,
    'Product',
    'Chennai',
    'INR',
    '2024-02-20'
),
(
    'T038',
    'C005',
    480000,
    320000,
    'Product',
    'Delhi',
    'INR',
    '2024-05-12'
),
(
    'T039',
    'C005',
    550000,
    360000,
    'Service',
    'Chennai',
    'INR',
    '2024-08-30'
),
(
    'T040',
    'C005',
    700000,
    450000,
    'Product',
    'Pune',
    'INR',
    '2024-11-25'
);

-- ==============================================================================
-- 5. AUDIT LOG TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS governance_schema.audit_logs (
    log_id STRING PRIMARY KEY,
    user_email STRING NOT NULL,
    role_name STRING NOT NULL,
    query_type STRING,
    accessed_object STRING,
    access_timestamp TIMESTAMP NOT NULL,
    company_context STRING
);

-- ==============================================================================
-- 6. BASE AGGREGATION VIEWS (not directly exposed)
-- ==============================================================================
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

-- ==============================================================================
-- 7. SECURE VIEWS 🔒 (THE ONLY EXPOSED OBJECTS)
-- ==============================================================================
-- These embed:
--   RLS (Row-Level Security)  → finance_user sees only their company
--   CLS (Column-Level Security) → auditor: profit masked, viewer: cost+profit masked
--
-- ROLE MATRIX:
--   admin        → All rows,   all columns
--   manager      → All rows,   all columns
--   finance_user → Own company, all columns
--   auditor      → All rows,   profit MASKED
--   viewer       → All rows,   cost + profit MASKED

-- A) Secure Yearly Revenue
CREATE OR REPLACE VIEW finance_schema.secure_revenue_yearly AS
SELECT
    v.company_id,
    v.year,
    v.total_revenue,
    -- COLUMN MASKING: cost
    CASE
        WHEN u.role_name = 'viewer' THEN NULL
        ELSE v.total_cost
    END AS total_cost,
    -- COLUMN MASKING: profit
    CASE
        WHEN u.role_name IN ('auditor', 'viewer') THEN NULL
        ELSE v.total_profit
    END AS total_profit
FROM finance_schema.revenue_yearly_view v
    JOIN governance_schema.users u ON u.email = current_user()
WHERE (
        u.role_name IN (
            'admin',
            'manager',
            'auditor',
            'viewer'
        )
    )
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
    CASE
        WHEN u.role_name = 'viewer' THEN NULL
        ELSE v.total_cost
    END AS total_cost,
    CASE
        WHEN u.role_name IN ('auditor', 'viewer') THEN NULL
        ELSE v.total_profit
    END AS total_profit
FROM finance_schema.revenue_quarterly_view v
    JOIN governance_schema.users u ON u.email = current_user()
WHERE (
        u.role_name IN (
            'admin',
            'manager',
            'auditor',
            'viewer'
        )
    )
    OR (
        u.role_name = 'finance_user'
        AND v.company_id = u.company_id
    );

-- ==============================================================================
-- 8. STRICT GRANTS (FINAL LOCKDOWN)
-- ==============================================================================
REVOKE ALL PRIVILEGES ON SCHEMA finance_schema FROM `users`;

REVOKE ALL PRIVILEGES ON SCHEMA governance_schema FROM `users`;

GRANT
SELECT ON VIEW finance_schema.secure_revenue_yearly TO `users`;

GRANT
SELECT ON VIEW finance_schema.secure_revenue_quarterly TO `users`;