import sys
sys.path.append("/Users/ganeshshinde/Documents/Ellliot Systems/flask-governed-api")
from db import run_query

print("=" * 70)
print("VERIFICATION: Does our setup match the architectural statement?")
print("=" * 70)

# 1. Check schemas exist (two domains: business + governance)
print("\n--- CHECK 1: Two separate schemas ---")
try:
    cols, rows = run_query("SHOW SCHEMAS IN governed_platform_catalog")
    for r in rows:
        print(f"  Schema: {r}")
except Exception as e:
    print(f"  ERROR: {e}")

# 2. Check business data: transactions table
print("\n--- CHECK 2: Transactions table (business data) ---")
try:
    cols, rows = run_query("DESCRIBE governed_platform_catalog.finance_schema.revenue_transactions")
    print(f"  Columns: {[r[0] for r in rows]}")
except Exception as e:
    print(f"  ERROR: {e}")

# 3. Check business data: aggregation views
print("\n--- CHECK 3: Aggregation views (business data) ---")
try:
    cols, rows = run_query("SELECT * FROM governed_platform_catalog.finance_schema.revenue_yearly_view LIMIT 2")
    print(f"  revenue_yearly_view columns: {cols}")
    print(f"  Sample rows: {rows[:2]}")
except Exception as e:
    print(f"  ERROR: {e}")

try:
    cols, rows = run_query("SELECT * FROM governed_platform_catalog.finance_schema.revenue_quarterly_view LIMIT 2")
    print(f"  revenue_quarterly_view columns: {cols}")
    print(f"  Sample rows: {rows[:2]}")
except Exception as e:
    print(f"  ERROR: {e}")

# 4. Check governance data: users table
print("\n--- CHECK 4: Users table (governance data) ---")
try:
    cols, rows = run_query("SELECT * FROM governed_platform_catalog.governance_schema.users")
    print(f"  Columns: {cols}")
    for r in rows:
        print(f"  User: {r}")
except Exception as e:
    print(f"  ERROR: {e}")

# 5. Check governance data: audit_logs table
print("\n--- CHECK 5: Audit logs table (governance data) ---")
try:
    cols, rows = run_query("DESCRIBE governed_platform_catalog.governance_schema.audit_logs")
    print(f"  Columns: {[r[0] for r in rows]}")
except Exception as e:
    print(f"  ERROR: {e}")

# 6. Check transactions belong to companies
print("\n--- CHECK 6: Transactions have company_id ---")
try:
    cols, rows = run_query("SELECT DISTINCT company_id FROM governed_platform_catalog.finance_schema.revenue_transactions LIMIT 10")
    print(f"  Companies in transactions: {[r[0] for r in rows]}")
except Exception as e:
    print(f"  ERROR: {e}")

# 7. Check users belong to companies and have roles
print("\n--- CHECK 7: Users have company_id + role_name ---")
try:
    cols, rows = run_query("SELECT email, role_name, company_id FROM governed_platform_catalog.governance_schema.users")
    for r in rows:
        print(f"  {r[0]:40s} role={r[1]:15s} company={r[2]}")
except Exception as e:
    print(f"  ERROR: {e}")

# 8. Check secure views exist and work
print("\n--- CHECK 8: Secure views exist and enforce policy ---")
try:
    cols, rows = run_query("SELECT * FROM governed_platform_catalog.finance_schema.secure_revenue_yearly LIMIT 3")
    print(f"  secure_revenue_yearly columns: {cols}")
    for r in rows:
        print(f"  Row: {r}")
except Exception as e:
    print(f"  ERROR: {e}")

# 9. Check current_user
print("\n--- CHECK 9: current_user() identity ---")
try:
    cols, rows = run_query("SELECT current_user()")
    current_email = rows[0][0]
    print(f"  current_user() = {current_email}")
    
    # Check role for current user
    cols2, rows2 = run_query(f"SELECT role_name, company_id FROM governed_platform_catalog.governance_schema.users WHERE email = '{current_email}'")
    if rows2:
        print(f"  Mapped role: {rows2[0][0]}, company: {rows2[0][1]}")
    else:
        print(f"  WARNING: current_user email NOT FOUND in users table!")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
