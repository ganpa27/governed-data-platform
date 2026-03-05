import sys
import os
sys.path.append("/Users/ganeshshinde/Documents/Ellliot Systems/flask-governed-api")
from db import run_query

print("Before Update:")
print(run_query("SELECT email, role_name FROM governed_platform_catalog.governance_schema.users WHERE email = 'ganesh.shinde@elliotsystems.com'"))

run_query("UPDATE governed_platform_catalog.governance_schema.users SET role_name = 'admin' WHERE email = 'ganesh.shinde@elliotsystems.com'")

print("After Update:")
print(run_query("SELECT email, role_name FROM governed_platform_catalog.governance_schema.users WHERE email = 'ganesh.shinde@elliotsystems.com'"))
