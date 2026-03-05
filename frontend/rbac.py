"""
rbac.py — Application-Level Role-Based Access Control
======================================================

Mirrors the exact logic from the Databricks secure views
(stage2_governance_architecture.sql).

Since Flask uses a single Databricks service token (admin),
the DB-level current_user() always returns admin. This module
enforces RBAC at the application layer so the UI role selector
actually controls what data the user sees.

─────────────────────────────────────────────────────────────
ROLE MATRIX  (5 roles, 8 transactions, 5 companies)
─────────────────────────────────────────────────────────────

  Role           │ Rows        │ Revenue │ Cost      │ Profit
  ───────────────┼─────────────┼─────────┼───────────┼──────────
  admin          │ ALL         │ ✅      │ ✅        │ ✅
  manager        │ ALL         │ ✅      │ ✅        │ ✅
  finance_user   │ Own company │ ✅      │ ✅        │ ✅
  auditor        │ ALL         │ ✅      │ ✅        │ ❌ HIDDEN
  viewer         │ ALL         │ ✅      │ ❌ HIDDEN  │ ❌ HIDDEN

NOTE: "HIDDEN" means the column is COMPLETELY REMOVED from the
      API response and the UI table. Users do NOT see a blank
      column — they simply see no column at all.

─────────────────────────────────────────────────────────────
USER → ROLE MAPPING  (mirrors governance_schema.users)
─────────────────────────────────────────────────────────────

  U001 Ganesh Shinde  │ admin        │ —
  U002 Priya Sharma   │ manager      │ —
  U003 Rahul Mehta    │ finance_user │ C001 (Elliot Systems)
  U004 Anita Desai    │ finance_user │ C002 (TechNova Solutions)
  U005 Vikram Joshi   │ auditor      │ —
  U006 Sara Khan      │ viewer       │ —
─────────────────────────────────────────────────────────────
"""

# Columns HIDDEN (removed entirely) for restricted roles
PROFIT_COLUMNS = {"total_profit", "profit_amount"}
COST_COLUMNS   = {"total_cost",   "cost_amount"}

# The column that identifies company ownership (used for RLS)
COMPANY_COLUMN = "company_id"

# Roles that see everything — no RLS, no CLS applied
FULL_ACCESS_ROLES = {"admin", "manager"}


def enforce_rbac(
    columns: list[str],
    rows: list[list],
    role: str,
    company_id: str | None = None,
) -> dict:
    """
    Apply RBAC rules to query results.

    Column-Level Security (CLS):
      COMPLETELY REMOVES disallowed columns from both the column headers
      and every data row. The UI will never see—or render—these columns.
      This replaces the old approach of setting cell values to NULL.

    Row-Level Security (RLS):
      finance_user — only their own company's rows are returned.

    Args:
        columns:    Column names from the query result
        rows:       Row data from the query result
        role:       admin | manager | finance_user | auditor | viewer
        company_id: Required for finance_user (e.g. "C001")

    Returns:
        A dict with the filtered columns, rows, and RBAC metadata.
    """
    role = (role or "admin").lower().strip()

    # ── Edge case: no data ────────────────────────────────────────────────────
    if not columns or not rows:
        return _pack(columns, rows or [], role, company_id,
                     detail="No data to enforce RBAC on.",
                     hidden=[], filtered=None)

    col_lower   = [c.lower() for c in columns]
    result_rows = [list(r) for r in rows]   # deep copy – never mutate caller's data
    hidden: list[str] = []                  # original names of dropped columns

    # ══════════════════════════════════════════════════════════════════════════
    # 1. COLUMN-LEVEL SECURITY — drop restricted columns completely
    # ══════════════════════════════════════════════════════════════════════════

    drop_indices: list[int] = []

    if role == "viewer":
        # viewer cannot see cost OR profit
        for i, col in enumerate(col_lower):
            if col in PROFIT_COLUMNS or col in COST_COLUMNS:
                hidden.append(columns[i])
                drop_indices.append(i)

    elif role == "auditor":
        # auditor cannot see profit (cost is fine)
        for i, col in enumerate(col_lower):
            if col in PROFIT_COLUMNS:
                hidden.append(columns[i])
                drop_indices.append(i)

    if drop_indices:
        drop_set    = set(drop_indices)
        # Remove from column list
        columns     = [c for i, c in enumerate(columns)   if i not in drop_set]
        col_lower   = [c for i, c in enumerate(col_lower) if i not in drop_set]
        # Remove same indices from every data row
        result_rows = [
            [cell for i, cell in enumerate(row) if i not in drop_set]
            for row in result_rows
        ]

    # ══════════════════════════════════════════════════════════════════════════
    # 2. ROW-LEVEL SECURITY — finance_user sees only their company
    # ══════════════════════════════════════════════════════════════════════════

    filtered: str | None = None

    if role == "finance_user":
        company_id = (company_id or "C001").upper().strip()

        if COMPANY_COLUMN in col_lower:
            comp_idx   = col_lower.index(COMPANY_COLUMN)
            before     = len(result_rows)
            result_rows = [
                r for r in result_rows
                if str(r[comp_idx]).upper() == company_id
            ]
            after = len(result_rows)
            filtered = (
                f"Showing {after} of {before} rows "
                f"(company {company_id} only)"
            )
        else:
            filtered = (
                "No company_id column in result — "
                "cannot enforce row-level filtering."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 3. ACCESS DETAIL MESSAGE (shown in the UI info card)
    # ══════════════════════════════════════════════════════════════════════════

    if role == "admin":
        detail = "Admin — full access to all rows and all columns."
    elif role == "manager":
        detail = "Manager — full access to all rows and all columns."
    elif role == "auditor":
        if hidden:
            detail = (
                f"Auditor access — all rows visible. "
                f"Columns not permitted for this role have been hidden: "
                f"{', '.join(hidden)}."
            )
        else:
            detail = "Auditor — all rows visible, no restricted columns in this result."
    elif role == "viewer":
        if hidden:
            detail = (
                f"Viewer access — all rows visible. "
                f"Columns not permitted for this role have been hidden: "
                f"{', '.join(hidden)}."
            )
        else:
            detail = "Viewer — all rows visible, no restricted columns in this result."
    elif role == "finance_user":
        detail = (
            f"Finance User ({company_id}) — "
            f"{len(result_rows)} rows accessible. Full financial detail."
        )
    else:
        detail      = f"Unknown role '{role}' — access denied."
        result_rows = []

    return _pack(columns, result_rows, role, company_id,
                 detail=detail, hidden=hidden, filtered=filtered)


def _pack(columns, rows, role, company_id, detail, hidden, filtered):
    """Build the standard RBAC result envelope."""
    return {
        "columns":         columns,
        "rows":            rows,
        "rows_returned":   len(rows) if rows else 0,
        "rbac_applied":    role not in FULL_ACCESS_ROLES,
        "rbac_role":       role,
        "rbac_company":    company_id if role == "finance_user" else None,
        "rbac_detail":     detail,
        "masked_columns":  hidden,   # kept for backward compat — these are now fully hidden
        "hidden_columns":  hidden,   # preferred name going forward
        "filtered_reason": filtered,
    }
