# STAGE 1 — DATABASE GOVERNANCE LAYER (ARCHITECTURE RECORD)

## 1. CATALOG STRUCTURE
| Level | Name |
|---|---|
| Catalog | `governed_platform_catalog` |

*(All objects exist inside this catalog.)*

---

## 2. SCHEMA STRUCTURE
| Schema Name | Purpose |
|---|---|
| `finance_schema` | Financial data + aggregation + secure views |
| `governance_schema` | User-role mapping + audit logs |

---

## 3. TABLES

### 3.1 `finance_schema.revenue_transactions` (RAW DATA - PROTECTED)
| Column Name | Data Type | Description | Sensitive? |
|---|---|---|---|
| transaction_id | STRING | Unique transaction identifier | No |
| company_id | STRING | Multi-tenant company key | Yes |
| revenue_amount| DOUBLE | Revenue per transaction | Yes |
| cost_amount | DOUBLE | Cost per transaction | Yes |
| created_at | TIMESTAMP| Transaction time | No |
| region | STRING | Geographic region | No |
| currency | STRING | Currency code | No |

**Access Rules:** Direct user, AI, and API access are **NOT ALLOWED**. Only aggregation views may read this.

### 3.2 `governance_schema.users` (ROLE MAPPING)
| Column Name | Data Type | Description |
|---|---|---|
| user_id | STRING | Unique user identifier |
| email | STRING | Login identity |
| role_name | STRING | admin / finance_user / auditor |
| company_id | STRING | Assigned company (for finance_user) |

**Access Rules:** Direct SELECT is **NOT ALLOWED**. Mapped dynamically inside secure views.

### 3.3 `governance_schema.audit_logs` (SYSTEM TRACKING)
| Column Name | Data Type | Description |
|---|---|---|
| log_id | STRING | Unique log ID |
| user_email | STRING | Who executed query |
| role_name | STRING | Role at execution |
| query_type | STRING | predefined / ai / router |
| accessed_object| STRING | View accessed |
| access_timestamp| TIMESTAMP| Execution time |
| company_context| STRING | Company filter context |

**Access Rules:** Direct SELECT is **NOT ALLOWED**. Written to by backend systems.

---

## 4. BASE VIEWS (AGGREGATION - PROTECTED)

### 4.1 `finance_schema.revenue_yearly_view`
| Column Name | Data Type | Derived From |
|---|---|---|
| company_id | STRING | revenue_transactions |
| year | INT | YEAR(created_at) |
| total_revenue | DOUBLE | SUM(revenue_amount) |
| total_cost | DOUBLE | SUM(cost_amount) |
| total_profit | DOUBLE | SUM(revenue - cost) |

**Access Rules:** Direct user access **NOT ALLOWED**. Used strictly by secure views.

### 4.2 `finance_schema.revenue_quarterly_view`
*(Identical to yearly view, but includes `quarter` column derived from `QUARTER(created_at)`)*.

---

## 5. SECURE VIEWS 🔒 (EXTERNAL EXPOSURE ONLY)

### 5.1 `finance_schema.secure_revenue_yearly`
| Column Name | Visible to Admin | Visible to Finance User | Visible to Auditor |
|---|---|---|---|
| company_id | ✅ | Only own company | ✅ |
| year | ✅ | Only own company | ✅ |
| total_revenue | ✅ | Only own company | ✅ |
| total_cost | ✅ | Only own company | ✅ |
| total_profit | ✅ | Only own company | ❌ NULL (Masked) |

### Row-Level Logic
| Role | Row Visibility |
|---|---|
| admin | All companies |
| finance_user | Only assigned company |
| auditor | All companies |

### 5.2 `finance_schema.secure_revenue_quarterly`
*(Identical rules, row-level logic, and masking as secure_revenue_yearly, plus quarter visibility).*

---

## 6. FINAL OBJECT TREE

```
governed_platform_catalog
│
├── finance_schema
│   ├── revenue_transactions          (Raw - Blocked)
│   ├── revenue_yearly_view           (Base - Blocked)
│   ├── revenue_quarterly_view        (Base - Blocked)
│   ├── secure_revenue_yearly         (Secure - Exposed)
│   └── secure_revenue_quarterly      (Secure - Exposed)
│
└── governance_schema
    ├── users                         (Mapping - Blocked)
    └── audit_logs                    (Tracking - Blocked)
```
