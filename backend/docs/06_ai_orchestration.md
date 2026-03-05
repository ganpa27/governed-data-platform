# 🤖 AI Orchestration & SQL Firewall

---

## 1. What This Document Covers

This document explains the most complex part of the platform — the **AI-powered natural language to SQL pipeline**. It covers:

- How Groq AI (Llama 3) generates SQL from plain English questions
- The per-request, role-aware + company-aware system prompt (critical RLS fix)
- The 5-layer SQL firewall that validates every AI-generated query
- The governance awareness layer that checks results after execution
- How masked columns are detected and how the system responds
- The AI summary generation pipeline (company-context-aware)
- Fallbacks when Groq is not configured

---

## 2. When the AI Engine Activates

The AI engine is NOT the first option. The system follows this priority order:

```
User types a question
    │
    ▼
Step 1: Keyword Router — tries to match to a predefined/company-scoped query
    │
    ├── Match found → Run predefined query (fast, free, safe)
    │
    ├── No match + Groq key configured → Step 2: AI Engine (with role+company context)
    │
    └── No match + no Groq key → Return LLM stub with suggestions
```

**Special RLS rule:** For `finance_user`, questions containing "our", "my", "we" are **always** routed to the AI engine — even if a keyword match exists — because the AI is the only path that can generate a correctly filtered `WHERE company_id = 'C001'` query for all question variants.

---

## 3. AI Configuration (.env)

```
GROQ_API_KEY=gsk_...           # API key from https://console.groq.com/keys
GROQ_MODEL=llama-3.3-70b-versatile    # Which Groq model to use
GROQ_BASE_URL=https://api.groq.com/openai/v1
AI_MAX_TOKENS=500              # Max tokens in the AI response
AI_TEMPERATURE=0.1             # Low temperature = more deterministic
```

We use the **Groq API** with the **OpenAI-compatible interface** (same SDK, different base URL). This means we can use the `openai` Python package to call Groq.

---

## 4. The System Prompt (Role-Aware + Company-Aware)

> **CRITICAL SECURITY FIX (Stage 4):** The system prompt is now a **function** (`_build_system_prompt(user_role, company_id)`), not a constant. It is rebuilt per-request and injects the user's exact role and company_id. This is what makes Row-Level Security work at the AI layer.

### Why a Dynamic Prompt?

Previously, the system prompt was a static constant. When Rahul (Finance User, C001) asked "What was our total profit in 2024?", the AI had no idea which company Rahul belongs to, so it generated:

```sql
-- WRONG (before fix): Returns ALL companies
SELECT SUM(total_profit) FROM ...secure_revenue_yearly WHERE year = 2024
```

Now the prompt includes:

```
CURRENT USER ROLE: FINANCE_USER
COMPANY RESTRICTION — THIS IS MANDATORY:
  - The user belongs ONLY to company C001 (Elliot Systems (Technology, Mumbai)).
  - You MUST always add WHERE company_id = 'C001' to EVERY query you generate.
  - NEVER generate a query that returns data for other companies.
  - If the user says 'our', 'my', 'we', it means company C001.
  - Even for aggregate queries (SUM, COUNT, AVG), always include WHERE company_id = 'C001'.
```

So the AI now generates:

```sql
-- CORRECT (after fix): Returns only Elliot Systems
SELECT year, SUM(total_profit) AS total_profit
FROM governed_platform_catalog.finance_schema.secure_revenue_yearly
WHERE company_id = 'C001' AND year = 2024
GROUP BY year
LIMIT 50
```

### Role-Specific Prompt Blocks

| Role | Prompt Block |
|------|-------------|
| `admin` | "Full access — you may query ALL companies without any WHERE filter." |
| `manager` | Same as admin. |
| `finance_user` | "MANDATORY: Always add `WHERE company_id = '{cid}'` to every query." |
| `auditor` | "Read-only, total_profit is masked (NULL) for this role." |
| `viewer` | "Read-only, total_profit and total_cost are both masked." |

### Full System Prompt Structure

```
You are a SQL generation assistant...

STRICT RULES:
1. Only SELECT statements.
2. Only secure_revenue_yearly or secure_revenue_quarterly (fully-qualified).
3. No UNION, JOIN, subqueries, CTEs, window functions.
4. No DDL/DML.
5. No blocked tables.
6. Output only raw SQL — no markdown, no code fences.
7. Always include LIMIT (max 100).
8. Output CANNOT_ANSWER if question is out of scope.

GOVERNANCE AWARENESS:
- total_profit may be NULL for auditor/viewer roles.
- Do not compute derived values from masked columns.

ALL COMPANY IDs AND NAMES:
  C001 = Elliot Systems (Technology, Mumbai)
  C002 = TechNova Solutions (IT Services, Bangalore)
  C003 = GreenField Industries (Manufacturing, Pune)
  C004 = Meridian Corp (Finance, Delhi)
  C005 = Atlas Dynamics (Automotive, Chennai)

Available columns: [per view]

CURRENT USER ROLE: [injected per request]
COMPANY RESTRICTION: [injected per request for finance_user]
```

---

## 5. The SQL Generation Pipeline (`generate_sql()`)

### Signature (Updated)

```python
def generate_sql(
    question:   str,
    user_role:  str = "admin",
    company_id: str | None = None,  # ← NEW: required for finance_user
) -> str:
```

### Step-by-Step Flow

```
1. Check if GROQ_API_KEY is set → If not, raise AIError

2. Build per-request system prompt:
   → _build_system_prompt(user_role, company_id)
   → Injects role-specific rules + mandatory WHERE clause for finance_user

3. Build user prompt:
   "User role: finance_user (company: C001)
    Question: What was our total profit in 2024?"

4. Send to Groq API:
   - System message: per-request prompt (above)
   - User message: question + role + company hint
   - Model: llama-3.3-70b-versatile
   - Temperature: 0.1 (deterministic, safe)
   - Max tokens: 500

5. Receive response:
   "SELECT year, SUM(total_profit) AS total_profit FROM
    governed_platform_catalog.finance_schema.secure_revenue_yearly
    WHERE company_id = 'C001' AND year = 2024 GROUP BY year LIMIT 50"

6. Clean output (strip markdown fences, whitespace)

7. Check for CANNOT_ANSWER → raise ValueError if so

8. Pass through 5-Layer SQL Firewall (validate_sql())

9. Inject LIMIT if missing (inject_limit())

10. Return validated SQL
```

---

## 6. The 5-Layer SQL Firewall (`validate_sql()`)

Every AI-generated SQL query must pass through 5 sequential validation layers. If any layer fails, the query is immediately rejected and never reaches the database.

### Layer 1: Statement Verification

```python
# Must start with SELECT
if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
    raise SQLValidationError("Only SELECT statements are permitted.")
```

### Layer 2: Keyword Blocking

```python
BLOCKED = r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|
             UNION|INTO|GRANT|REVOKE|MERGE|CALL|PRAGMA|SHOW|DESCRIBE)\b"
```

### Layer 3: Target Enforcement

```python
ALLOWED_VIEWS = {
    "governed_platform_catalog.finance_schema.secure_revenue_yearly",
    "governed_platform_catalog.finance_schema.secure_revenue_quarterly",
}
if not any(view in sql_lower for view in ALLOWED_VIEWS):
    raise SQLValidationError("Query must target only governed views.")
```

### Layer 4: Schema Blocking

```python
BLOCKED_TABLES = r"\b(revenue_transactions|raw_revenue|audit_logs|users|governance_schema)\b"
```

### Layer 5: Stack Prevention

```python
# No semicolons followed by more content
if re.search(r";.*\S", sql, re.DOTALL):
    raise SQLValidationError("Stacked SQL statements are not allowed.")
```

### Firewall Summary

| Layer | Name | What It Catches |
|-------|------|-----------------|
| 1 | Statement Check | Non-SELECT queries |
| 2 | Keyword Block | DROP, DELETE, UPDATE, INSERT, UNION, etc. |
| 3 | Target Check | Queries not targeting secure views |
| 4 | Schema Block | References to governance_schema, raw tables |
| 5 | Stack Check | Multiple statements via semicolons |

---

## 7. Role-Based LIMIT Injection

```python
ROLE_ROW_CAPS = {
    "admin":        100,
    "manager":      100,
    "finance_user": 50,
    "auditor":      50,
    "viewer":       20,
}

def inject_limit(sql: str, role: str = "admin") -> str:
    if re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return sql   # Already has a LIMIT
    cap = ROLE_ROW_CAPS.get(role, 20)
    return f"{sql} LIMIT {cap}"
```

---

## 8. Governance Awareness Layer (Post-Execution)

### Why

Even after the firewall validates the SQL, the Databricks secure view might mask columns (e.g., `total_profit = NULL` for auditors). Without detection, the AI would generate a misleading summary from NULL data.

### How It Works

**A. `detect_masked_columns()`** — Is the entire `total_profit` column NULL?

**B. `detect_analytical_dependency()`** — Does the question require profit data?

**C. `build_governance_report()`** — Combines both:

```
IF masked AND question needs profit analysis:
    → status: "limited"
    → Block AI summary, show "Access Denied" alert

IF masked BUT question doesn't need profit:
    → status: "ok"
    → Show data normally (profit shows as "—")

IF no masking:
    → status: "ok"
    → Normal output
```

---

## 9. AI Summary Generation (`generate_summary()`)

### Signature (Updated)

```python
def generate_summary(
    question:          str,
    columns:           list,
    rows:              list,
    governance_status: str = "ok",
    masked_columns:    list[str] = None,
    user_role:         str = "admin",   # ← NEW
    company_id:        str | None = None,  # ← NEW
) -> str:
```

### Company-Context-Aware Summary (Critical Fix)

For `finance_user`, the summary prompt now includes:

```
IMPORTANT CONTEXT: This data belongs to Elliot Systems (C001) only.
When writing the summary, always refer to the company by name (Elliot Systems)
and make clear this is Elliot Systems's data, not platform-wide data.
```

This prevents the AI from saying "Our total profit across all 5 companies is $4,715,000" when it should say "Elliot Systems's total profit in 2024 was $X."

### Summary Uses Smaller Model

```python
model="llama-3.1-8b-instant"  # Fast, efficient for summarization
```

---

## 10. Keyword Router (Role-Aware)

### Updated `route_question()` Signature

```python
def route_question(
    question:   str,
    user_role:  str = "admin",
    company_id: str | None = None,
) -> dict:
```

### New Finance User Rules

| Question Pattern | Old Behavior | New Behavior |
|-----------------|-------------|-------------|
| "our total profit" | Routes to `summary` (all companies) | Routes to AI → generates WHERE company_id filter |
| "total profit in 2024" (finance_user) | Routes to `year_filter` (all companies) | Routes to `company_summary_year` (C001 only) |
| "platform summary" (finance_user) | Returns all 5 companies' aggregate | Returns C001-only aggregate |

### Priority Order (Updated)

1. Company + quarterly combo (explicit company ID in question)
2. Company yearly (explicit company ID in question)
3. Finance user "our/my" questions → **route to AI** (critical RLS)
4. Platform summary → finance_user gets company_summary, others get full summary
5. Quarter number filter
6. Year filter (finance_user with year → company_summary_year)
7. Top cost
8. Top profit
9. Top revenue
10. Quarterly (all)
11. Yearly (all)
12. Generic
13. No match → AI

---

## 11. Complete AI Pipeline Flow (Finance User Example)

```
Rahul (finance_user, C001) asks: "What was our total profit in 2024?"
    │
    ▼
Step 1: Keyword router
    route_question(q, user_role="finance_user", company_id="C001")
    │   → "our" + "profit" + finance_user → matched=False → route to AI
    │
    ▼
Step 2: generate_sql(question, user_role="finance_user", company_id="C001")
    │   → _build_system_prompt injects:
    │     "MANDATORY: WHERE company_id = 'C001' in EVERY query"
    │   → Groq generates:
    │     SELECT year, SUM(total_profit) AS total_profit
    │     FROM ...secure_revenue_yearly
    │     WHERE company_id = 'C001' AND year = 2024
    │     GROUP BY year LIMIT 50
    │
    ▼
Step 3: SQL Firewall — all 5 layers pass ✅
    │
    ▼
Step 4: LIMIT injection — already present ✅
    │
    ▼
Step 5: Databricks executes query
    │   → Returns only C001 rows (RLS enforced at two layers now)
    │
    ▼
Step 6: RBAC (rbac.py) — further filters to C001 only ✅
    │
    ▼
Step 7: Governance check — no masking for finance_user ✅
    │
    ▼
Step 8: generate_summary(..., user_role="finance_user", company_id="C001")
    │   → Prompt includes: "This is Elliot Systems's data only."
    │   → Summary mentions company name correctly
    │
    ▼
Dashboard shows: "Elliot Systems's total profit in 2024 was $X,XXX,XXX"
    RBAC badge: "Finance User — C001 Only"
    Data table: only 1 row (C001)
```

---

## 12. Error Handling

| Error Type | When It Happens | User Sees |
|-----------|-----------------|-----------|
| `AIError` | Groq API key missing, network failure | "AI engine error" message |
| `SQLValidationError` | AI generated unsafe SQL | "AI engine error" message (query never runs) |
| `ValueError` | AI responded CANNOT_ANSWER | "No Route Matched" with suggestions |
| Query execution failure | Databricks error | "Query execution failed" message |

---

*Next: See `07_databricks_setup.md` for how to set up the entire Databricks environment from scratch.*
