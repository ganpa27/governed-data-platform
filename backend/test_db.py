import sys
import os
sys.path.append("/Users/ganeshshinde/Documents/Ellliot Systems/flask-governed-api")
from db import run_query

print("Current Databricks User:", run_query("SELECT current_user()"))
print("Governance Users:", run_query("SELECT * FROM governed_platform_catalog.governance_schema.users"))
print("Secure Yearly Revenue:", run_query("SELECT * FROM governed_platform_catalog.finance_schema.secure_revenue_yearly LIMIT 1"))
