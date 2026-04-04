# Lane B Implementation Plan — Exact File-Change Plan

**Scope:** `employee_roles`, all `employees_legacy_%` tables  
**Decision:** Option A (drop only)  
**Status:** Plan only — DO NOT EXECUTE until approved.

---

## 1. Code Cleanup Report

### Files to modify or remove

| File | Classification | Action |
|------|----------------|--------|
| `app/routers/employees.py` | **Remove now** | Delete file — dead router; depends on non-existent `employees` table and `EmployeeRole`. |
| `app/models/employee_role.py` | **Remove now** | Delete file — `EmployeeRole` maps to `employee_roles`; table is being dropped. |
| `app/models/employee.py` | **Remove now** | Delete file — shim for `Employee`; only used by employees router. |
| `app/schemas/employee_role.py` | **Remove now** | Delete file — only used by employees router. |
| `app/schemas/employee.py` | **Remove now** | Delete file — only used by employees router. |
| `app/models/payee.py` | **Refactor now** | Remove `Employee` class (lines 69–96) — maps to non-existent `employees`; no remaining use after router removal. |
| `app/models/__init__.py` | **Refactor now** | Remove `Employee` from payee imports; remove `EmployeeRole` import line. |
| `app/main.py` | **Refactor now** | Remove `employees_router` import and `app.include_router(employees_router)`. |

### Keep temporarily

| Item | Reason |
|------|--------|
| *(none)* | All Lane B–related code is either removed or refactored. |

### Refactor later (out of Lane B scope)

| Item | Reason |
|------|--------|
| Payee-backed employees design | If reintroduced, add `Employee` model + migrations when `payees`/`employees` schema is finalized. |

### Summary by action

- **Delete:** `app/routers/employees.py`, `app/models/employee_role.py`, `app/models/employee.py`, `app/schemas/employee_role.py`, `app/schemas/employee.py`
- **Edit:** `app/models/payee.py` (remove `Employee` class), `app/models/__init__.py` (remove exports), `app/main.py` (remove router)

---

## 2. Implementation Plan

### A. Alembic migration

**New file:** `alembic_tenant/versions/g2b3c4d5e6f7_drop_lane_b_legacy_employees.py`

```python
"""Drop Lane B legacy tables (employee_roles, employees_legacy_*)

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-15

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "g2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Drop FK from employee_roles to employees_legacy_* (if table exists)
    if insp.has_table("employee_roles"):
        for fk in insp.get_foreign_keys("employee_roles"):
            if fk.get("referred_table", "").startswith("employees_legacy_"):
                op.drop_constraint(fk["name"], "employee_roles", type_="foreignkey")
                break

    # 2. Drop employee_roles
    op.execute(sa.text("DROP TABLE IF EXISTS employee_roles CASCADE"))

    # 3. Drop all employees_legacy_* tables (dynamic date suffix per tenant)
    result = bind.execute(
        sa.text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename LIKE 'employees_legacy_%'"
        )
    )
    for (tablename,) in result:
        # Identifier-safe: tablename from pg_tables; quote to handle any chars
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{tablename}" CASCADE'))


def downgrade() -> None:
    pass
```

**Idempotency:** `DROP TABLE IF EXISTS` and FK check via inspector are idempotent. The `employees_legacy_%` loop drops only tables that exist.

**Note:** The FK check uses `referred_table` — SQLAlchemy inspector returns the actual target table name (e.g. `employees_legacy_20260305`), so `startswith("employees_legacy_")` will match.

### B. Code cleanup (exact edits)

#### 1. `app/main.py`

**Remove:**
```python
from app.routers.employees import router as employees_router
```
```python
app.include_router(employees_router)
```

#### 2. `app/models/__init__.py`

**Remove from payee import:** `Employee,`
**Remove:** `from app.models.employee_role import EmployeeRole`

#### 3. `app/models/payee.py`

**Remove the entire `Employee` class** (lines 69–96 inclusive), including the blank line before `class CompensationProfile`.

#### 4. Delete files

- `app/routers/employees.py`
- `app/models/employee_role.py`
- `app/models/employee.py`
- `app/schemas/employee_role.py`
- `app/schemas/employee.py`

---

## 3. Verification Proof Required

### 3.1 Tenant_demo after upgrade head

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh'
```

**Proof — no Lane B tables:**
```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -t -c "
SELECT tablename FROM pg_tables 
WHERE schemaname='public' 
  AND (tablename = 'employee_roles' OR tablename LIKE 'employees_legacy_%');
"
```
→ **0 rows**

### 3.2 Fresh empty tenant DB → upgrade head

1. Create `tenant_test`, run upgrade head.
2. Same query as above.
3. **Expected:** 0 rows (no `employee_roles`, no `employees_legacy_%`).

### 3.3 Autogenerate does not propose recreation

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini revision --autogenerate -m "test_lane_b_no_recreate"'
```

**Expected:** No "Detected added table 'employee_roles'" and no "Detected added table 'employees_legacy_*'". Delete generated revision if created for testing only.

### 3.4 App startup / imports / tests

```bash
docker compose -f docker-compose.yml build truckerp-api \
  && docker compose -f docker-compose.yml up -d truckerp-api
docker logs truckerp-api --tail 30
```

**Expected:** No import errors; app starts.

```bash
cd /home/admin/trucking_erp && python -m pytest tests/ -v --tb=short -x 2>&1 | head -80
```

**Expected:** No failures from missing Employee/EmployeeRole/employees imports.

---

## 4. Execution order

1. Create Alembic migration `g2b3c4d5e6f7_drop_lane_b_legacy_employees.py`
2. Apply code edits (main.py, models/__init__.py, payee.py)
3. Delete the five files
4. Rebuild API and run tenant upgrade
5. Run verification commands
6. Run autogenerate check
7. Run tests

---

## 5. Files changed summary

| Action | File |
|--------|------|
| **New** | `alembic_tenant/versions/g2b3c4d5e6f7_drop_lane_b_legacy_employees.py` |
| **Edit** | `app/main.py` (remove 2 lines) |
| **Edit** | `app/models/__init__.py` (remove 2 imports) |
| **Edit** | `app/models/payee.py` (remove Employee class) |
| **Delete** | `app/routers/employees.py` |
| **Delete** | `app/models/employee_role.py` |
| **Delete** | `app/models/employee.py` |
| **Delete** | `app/schemas/employee_role.py` |
| **Delete** | `app/schemas/employee.py` |
