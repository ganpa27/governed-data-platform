"""
migrate_stage2.py — Execute Stage 2 data upgrade against Databricks.
Inserts using explicit column names to match the ACTUAL Databricks table schemas.
"""
import sys
sys.path.insert(0, "/Users/ganeshshinde/Documents/Ellliot Systems/flask-governed-api")
from db import run_query

STATEMENTS = [
    # ── Companies (schema: company_id, company_name, industry, country, created_at, is_active) ──
    "DELETE FROM governed_platform_catalog.finance_schema.companies",

    """INSERT INTO governed_platform_catalog.finance_schema.companies
       (company_id, company_name, industry, country, created_at, is_active) VALUES
      ('C001', 'Elliot Systems',        'Technology',     'India', current_timestamp(), TRUE),
      ('C002', 'TechNova Solutions',    'IT Services',    'India', current_timestamp(), TRUE),
      ('C003', 'GreenField Industries', 'Manufacturing',  'India', current_timestamp(), TRUE),
      ('C004', 'Meridian Corp',         'Finance',        'India', current_timestamp(), TRUE),
      ('C005', 'Atlas Dynamics',        'Automotive',     'India', current_timestamp(), TRUE)""",

    # ── Transactions ──
    # Schema: transaction_id, company_id, transaction_date, revenue_type, region,
    #         revenue_amount, cost_amount, profit_amount, currency, created_at
    "DELETE FROM governed_platform_catalog.finance_schema.revenue_transactions",

    # C001 — Elliot Systems (Technology, Mumbai) — 2023
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T001','C001','2023-02-15','Product',     'Mumbai',   250000,140000,110000,'INR','2023-02-15'),
      ('T002','C001','2023-05-22','Service',     'Mumbai',   180000, 95000, 85000,'INR','2023-05-22'),
      ('T003','C001','2023-08-10','Product',     'Pune',     320000,175000,145000,'INR','2023-08-10'),
      ('T004','C001','2023-11-28','Subscription','Mumbai',   150000, 80000, 70000,'INR','2023-11-28')""",

    # C001 — 2024
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T005','C001','2024-01-18','Product',     'Mumbai',   350000,190000,160000,'INR','2024-01-18'),
      ('T006','C001','2024-04-25','Service',     'Pune',     200000,110000, 90000,'INR','2024-04-25'),
      ('T007','C001','2024-07-12','Subscription','Mumbai',   280000,155000,125000,'INR','2024-07-12'),
      ('T008','C001','2024-10-05','Product',     'Delhi',    420000,230000,190000,'INR','2024-10-05')""",

    # C002 — TechNova Solutions (IT Services, Bangalore) — 2023
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T009','C002','2023-03-10','Service',     'Bangalore',180000,100000, 80000,'INR','2023-03-10'),
      ('T010','C002','2023-06-18','Subscription','Bangalore', 95000, 55000, 40000,'INR','2023-06-18'),
      ('T011','C002','2023-09-22','Service',     'Chennai',  210000,120000, 90000,'INR','2023-09-22'),
      ('T012','C002','2023-12-05','Product',     'Bangalore',130000, 70000, 60000,'INR','2023-12-05')""",

    # C002 — 2024
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T013','C002','2024-02-14','Service',     'Bangalore',220000,115000,105000,'INR','2024-02-14'),
      ('T014','C002','2024-05-20','Subscription','Chennai',  155000, 85000, 70000,'INR','2024-05-20'),
      ('T015','C002','2024-08-08','Service',     'Bangalore',280000,150000,130000,'INR','2024-08-08'),
      ('T016','C002','2024-11-15','Product',     'Hyderabad',170000, 90000, 80000,'INR','2024-11-15')""",

    # C003 — GreenField Industries (Manufacturing, Pune) — 2023
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T017','C003','2023-01-20','Product',     'Pune',     400000,260000,140000,'INR','2023-01-20'),
      ('T018','C003','2023-04-15','Product',     'Mumbai',   350000,230000,120000,'INR','2023-04-15'),
      ('T019','C003','2023-07-25','Product',     'Delhi',    280000,190000, 90000,'INR','2023-07-25'),
      ('T020','C003','2023-10-30','Service',     'Pune',     310000,200000,110000,'INR','2023-10-30')""",

    # C003 — 2024
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T021','C003','2024-01-12','Product',     'Pune',     450000,280000,170000,'INR','2024-01-12'),
      ('T022','C003','2024-04-18','Product',     'Mumbai',   380000,245000,135000,'INR','2024-04-18'),
      ('T023','C003','2024-07-22','Product',     'Chennai',  520000,310000,210000,'INR','2024-07-22'),
      ('T024','C003','2024-10-28','Service',     'Pune',     290000,180000,110000,'INR','2024-10-28')""",

    # C004 — Meridian Corp (Finance, Delhi) — 2023
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T025','C004','2023-02-28','Service',     'Delhi',    190000,120000, 70000,'INR','2023-02-28'),
      ('T026','C004','2023-05-10','Subscription','Mumbai',   160000,100000, 60000,'INR','2023-05-10'),
      ('T027','C004','2023-08-18','Service',     'Delhi',    220000,140000, 80000,'INR','2023-08-18'),
      ('T028','C004','2023-11-22','Product',     'Bangalore',175000,110000, 65000,'INR','2023-11-22')""",

    # C004 — 2024
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T029','C004','2024-03-08','Service',     'Delhi',    240000,155000, 85000,'INR','2024-03-08'),
      ('T030','C004','2024-06-15','Subscription','Mumbai',   195000,125000, 70000,'INR','2024-06-15'),
      ('T031','C004','2024-08-25','Service',     'Delhi',    310000,195000,115000,'INR','2024-08-25'),
      ('T032','C004','2024-12-01','Product',     'Pune',     180000,115000, 65000,'INR','2024-12-01')""",

    # C005 — Atlas Dynamics (Automotive, Chennai) — 2023
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T033','C005','2023-03-05','Product',     'Chennai',  500000,350000,150000,'INR','2023-03-05'),
      ('T034','C005','2023-06-22','Product',     'Bangalore',420000,290000,130000,'INR','2023-06-22'),
      ('T035','C005','2023-09-15','Service',     'Chennai',  380000,250000,130000,'INR','2023-09-15'),
      ('T036','C005','2023-12-18','Product',     'Mumbai',   550000,370000,180000,'INR','2023-12-18')""",

    # C005 — 2024
    """INSERT INTO governed_platform_catalog.finance_schema.revenue_transactions
       (transaction_id, company_id, transaction_date, revenue_type, region, revenue_amount, cost_amount, profit_amount, currency, created_at) VALUES
      ('T037','C005','2024-02-20','Product',     'Chennai',  600000,400000,200000,'INR','2024-02-20'),
      ('T038','C005','2024-05-12','Product',     'Delhi',    480000,320000,160000,'INR','2024-05-12'),
      ('T039','C005','2024-08-30','Service',     'Chennai',  550000,360000,190000,'INR','2024-08-30'),
      ('T040','C005','2024-11-25','Product',     'Pune',     700000,450000,250000,'INR','2024-11-25')""",

    # ── Views (unchanged — they read from transactions) ───────────────────────
    """CREATE OR REPLACE VIEW governed_platform_catalog.finance_schema.revenue_yearly_view AS
    SELECT company_id, YEAR(created_at) AS year,
           SUM(revenue_amount) AS total_revenue,
           SUM(cost_amount) AS total_cost,
           SUM(revenue_amount - cost_amount) AS total_profit
    FROM governed_platform_catalog.finance_schema.revenue_transactions
    GROUP BY company_id, YEAR(created_at)""",

    """CREATE OR REPLACE VIEW governed_platform_catalog.finance_schema.revenue_quarterly_view AS
    SELECT company_id, YEAR(created_at) AS year, QUARTER(created_at) AS quarter,
           SUM(revenue_amount) AS total_revenue,
           SUM(cost_amount) AS total_cost,
           SUM(revenue_amount - cost_amount) AS total_profit
    FROM governed_platform_catalog.finance_schema.revenue_transactions
    GROUP BY company_id, YEAR(created_at), QUARTER(created_at)""",

    # ── Secure views with 5-role RBAC ─────────────────────────────────────────
    """CREATE OR REPLACE VIEW governed_platform_catalog.finance_schema.secure_revenue_yearly AS
    SELECT v.company_id, v.year, v.total_revenue,
        CASE WHEN u.role_name = 'viewer' THEN NULL ELSE v.total_cost END AS total_cost,
        CASE WHEN u.role_name IN ('auditor','viewer') THEN NULL ELSE v.total_profit END AS total_profit
    FROM governed_platform_catalog.finance_schema.revenue_yearly_view v
    JOIN governed_platform_catalog.governance_schema.users u ON u.email = current_user()
    WHERE u.role_name IN ('admin','manager','auditor','viewer')
       OR (u.role_name = 'finance_user' AND v.company_id = u.company_id)""",

    """CREATE OR REPLACE VIEW governed_platform_catalog.finance_schema.secure_revenue_quarterly AS
    SELECT v.company_id, v.year, v.quarter, v.total_revenue,
        CASE WHEN u.role_name = 'viewer' THEN NULL ELSE v.total_cost END AS total_cost,
        CASE WHEN u.role_name IN ('auditor','viewer') THEN NULL ELSE v.total_profit END AS total_profit
    FROM governed_platform_catalog.finance_schema.revenue_quarterly_view v
    JOIN governed_platform_catalog.governance_schema.users u ON u.email = current_user()
    WHERE u.role_name IN ('admin','manager','auditor','viewer')
       OR (u.role_name = 'finance_user' AND v.company_id = u.company_id)""",
]


def main():
    total = len(STATEMENTS)
    print(f"{'='*70}")
    print(f"  Stage 2 Migration — {total} statements to execute on Databricks")
    print(f"{'='*70}\n")

    success = 0
    for i, sql in enumerate(STATEMENTS, 1):
        label = sql.strip()[:80].replace('\n', ' ')
        print(f"[{i:2d}/{total}] {label}...")
        try:
            run_query(sql)
            print(f"       ✅ OK")
            success += 1
        except Exception as e:
            print(f"       ❌ ERROR: {e}")

    print(f"\n{'='*70}")
    print(f"  Done: {success}/{total} statements succeeded")
    print(f"{'='*70}")

    # ── Verification ──────────────────────────────────────────────────────────
    print("\n── Verification ──────────────────────────────────────────")
    try:
        cols, rows = run_query("SELECT company_id, company_name, industry FROM governed_platform_catalog.finance_schema.companies ORDER BY company_id")
        print(f"\n📦 Companies ({len(rows)}):")
        for r in rows:
            print(f"   {r[0]} │ {r[1]:25s} │ {r[2]}")
    except Exception as e:
        print(f"   ❌ {e}")

    try:
        cols, rows = run_query("SELECT user_id, full_name, role_name, company_id FROM governed_platform_catalog.governance_schema.users ORDER BY user_id")
        print(f"\n👤 Users ({len(rows)}):")
        for r in rows:
            print(f"   {r[0]} │ {r[1]:18s} │ {r[2]:15s} │ {r[3] or '—'}")
    except Exception as e:
        print(f"   ❌ {e}")

    try:
        cols, rows = run_query("SELECT COUNT(*) FROM governed_platform_catalog.finance_schema.revenue_transactions")
        print(f"\n📊 Transactions: {rows[0][0]} rows")
    except Exception as e:
        print(f"   ❌ {e}")

    try:
        cols, rows = run_query("SELECT company_id, year, total_revenue, total_cost, total_profit FROM governed_platform_catalog.finance_schema.secure_revenue_yearly ORDER BY company_id, year")
        print(f"\n📈 Yearly Revenue ({len(rows)} rows):")
        for r in rows:
            print(f"   {r[0]} │ {r[1]} │ Rev: ₹{r[2]:>10,.0f} │ Cost: ₹{r[3]:>10,.0f} │ Profit: ₹{r[4]:>10,.0f}")
    except Exception as e:
        print(f"   ❌ {e}")


if __name__ == "__main__":
    main()
