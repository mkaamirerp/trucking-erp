# Lane B — Legacy Employees Report

**Scope:** `employees_legacy_20260305`, `employee_roles`  
**Status:** Analysis only — DO NOT DROP until approved.

---

## 1. DB Dependency Report

### Row counts (tenant_demo)

| Table | Rows |
|-------|------|
| employees_legacy_20260305 | 0 |
| employee_roles | 0 |

### Inbound / outbound foreign keys

| Direction | Constraint | From | To |
|-----------|------------|------|-----|
| **Outbound** | `employee_roles_employee_id_fkey` | employee_roles.employee_id | employees_legacy_20260305.id |

- **employees_legacy_20260305:** No inbound FKs (nothing references it except employee_roles).
- **employee_roles:** One outbound FK — `employee_id` → `employees_legacy_20260305.id`. No other tables reference employee_roles.

### Exact dependency

```
employee_roles.employee_id --[FK CASCADE]--> employees_legacy_20260305.id
```

**Blocking:** To drop `employees_legacy_20260305`, you must first drop the FK from `employee_roles`, then drop `employee_roles`, then drop `employees_legacy_20260305`.

### Indexes

| Table | Index | Type |
|-------|-------|------|
| employee_roles | employee_roles_pkey | PRIMARY KEY |
| employee_roles | ix_employee_roles_role | B-tree |
| employee_roles | ix_employee_roles_tenant_employee | B-tree |
| employee_roles | uq_employee_roles_tenant_employee_role | UNIQUE |
| employees_legacy_20260305 | employees_pkey | PRIMARY KEY |
| employees_legacy_20260305 | ix_employees_email | B-tree |
| employees_legacy_20260305 | ix_employees_tenant_code | B-tree (unique) |
| employees_legacy_20260305 | ix_employees_tenant_id | B-tree |

### Triggers / functions

- **Triggers:** None beyond PostgreSQL’s built-in FK triggers (`RI_FKey_cascade_del`, `RI_FKey_noaction_upd`, `RI_FKey_check_ins`, `RI_FKey_check_upd`).
- **Custom functions:** None on these tables.

### Views / materialized views

- None reference `employee_roles` or `employees_legacy_20260305`.

### Column structures

**employees_legacy_20260305** (from 5c9de38d8b3e, renamed by b8):
- id, tenant_id, employee_code, first_name, last_name, phone, email, hire_date, termination_date, is_active, created_at, updated_at

**employee_roles** (from 5c9de38d8b3e):
- id, tenant_id, employee_id, role, is_primary, created_at, updated_at

---

## 2. Code Usage Report

### Backend code references

| File | Usage |
|------|-------|
| `app/main.py` L20, L72 | `employees_router` included |
| `app/models/employee_role.py` | `EmployeeRole` model; `employee_id` → `ForeignKey("employees.id")` |
| `app/models/employee.py` | Shim → `app.models.payee.Employee` |
| `app/models/payee.py` L69-96 | `Employee` model; `__tablename__ = "employees"` (payee-backed) |
| `app/routers/employees.py` | Full CRUD + roles: create/list/get/update employees; add/list/delete employee roles |
| `app/schemas/employee.py` | `EmployeeCreate`, `EmployeeOut`, `EmployeeUpdate` |
| `app/schemas/employee_role.py` | `EmployeeRoleCreate`, `EmployeeRoleOut`, `ROLE_CHOICES` |
| `app/models/__init__.py` L14, L31 | Exports `Employee`, `EmployeeRole` |

### Model references

- **EmployeeRole** references `employees.id` in SQLAlchemy, but the DB FK targets `employees_legacy_20260305.id` (b8 renamed `employees` without updating `employee_roles`).
- **Employee** maps to `employees` (payee-backed), which does **not** exist in tenant_demo (and may not in other tenant DBs).

### Schema references

- `app/schemas/employee_role.py`: `EmployeeRoleCreate`, `EmployeeRoleOut`, `ROLE_CHOICES` (DRIVER, DISPATCHER, etc.).

### Router / service references

- `app/routers/employees.py`: `/api/v1/employees` router depends on `Employee` and `EmployeeRole`. It will fail where `employees` is missing (e.g. tenant_demo), since the underlying table does not exist.

### Migration references

| Migration | Relevance |
|-----------|-----------|
| `5c9de38d8b3e` | Creates `employees`, `employee_roles` (employee_id → employees.id) |
| `7f8e2b1e7e7f` | Adds unique constraint on employee_roles |
| `b8f9cfe34f1b` | Renames `employees` → `employees_legacy_YYYYMMDD`; no creation of new `employees` |

**Critical:** The payee-backed `employees` table expected by the `Employee` model is never created by tenant migrations. B8 only renames; no later migration creates the new `employees` table.

### Test references

- No tests reference `employees`, `EmployeeRole`, or the employees router.

---

## 3. Architecture Fit Report

### People-first model (current, locked)

```
people (tenant_id, id, first_name, last_name, email, ...)
  └── person_roles (tenant_id, person_id, role_code, is_primary, is_active)
  └── driver_profiles (tenant_id, person_id, license_number, ...)
        └── drivers (legacy; person_id links to people)
```

- Identity: `people` + `platform_users` (platform DB).
- Roles: `person_roles.role_code` (e.g. DRIVER, DISPATCHER).
- Driver-specific: `driver_profiles` + optional `drivers`.

### Legacy employee model

```
employees (5c9de38d8b3e) / employees_legacy_* (renamed by b8)
  └── employee_roles (tenant_id, employee_id, role, is_primary)
```

- Old identity: `employees` (first_name, last_name, email, employee_code).
- Roles: `employee_roles.role` (DRIVER, DISPATCHER, MANAGER, etc.).

### Intended payee-backed model (never deployed)

```
payees (worker_type, payee_type, display_name, ...)
  └── employees (payee_id, employee_number, hire_date, ...)
        └── employee_roles (employee_id, role, is_primary)
```

### Mapping to people-first

| Legacy | People-first equivalent |
|--------|---------------------------|
| employees_legacy (person + employment) | `people` (identity) + `person_roles` (role) |
| employee_roles.role | `person_roles.role_code` |
| employees_legacy.first_name, last_name, email | `people` fields |
| employees_legacy.employee_code | Could map to `person_roles` metadata or custom field |

The employees/employee_roles design predates people-first and duplicates its role semantics.

---

## 4. Classification

### employees_legacy_20260305

| Factor | Finding |
|--------|---------|
| Row count | 0 |
| References | Only `employee_roles.employee_id` |
| Code usage | None; `Employee` model uses `employees`, which does not exist |
| Schema validation | Not required |
| People-first | Replaced by `people` + `person_roles` |

**Classification: SAFE TO DROP NOW**

- Empty table.
- Only dependent is `employee_roles`.
- No live code path using it.
- Effectively orphaned since b8 rename.

### employee_roles

| Factor | Finding |
|--------|---------|
| Row count | 0 |
| References | FK to employees_legacy_20260305 |
| Code usage | Routers and models expect it; `/employees` flow broken (no `employees` table) |
| Schema validation | Not required |
| People-first | Replaced by `person_roles` |

**Classification: SAFE TO DROP NOW**

- Empty table.
- The `/api/v1/employees` flow is non-functional (target `employees` table missing).
- Role semantics are covered by `person_roles`.
- Dropping does not weaken a working feature.

---

## 5. Permanent Fix Plan

### Option A: Drop only (recommended)

Both tables are empty and unused. Dropping is safe.

**Migration steps:**

1. Add a tenant migration after head:
   - Drop FK `employee_roles_employee_id_fkey`.
   - `DROP TABLE IF EXISTS employee_roles CASCADE`.
   - `DROP TABLE IF EXISTS employees_legacy_20260305 CASCADE` (or parameterize legacy name if needed).

2. Code changes:
   - Remove `employees_router` from `app/main.py`.
   - Remove or deprecate `app/routers/employees.py`.
   - Remove `EmployeeRole` model and related imports.
   - Keep `Employee` if payees/employees will be built later; otherwise remove or clearly mark as future-only.

3. Prevent recreation:
   - `EmployeeRole` not in metadata → autogenerate will not recreate.
   - `employees_legacy_*` never in metadata → will not be recreated.
   - Stop b8 from creating `employees_legacy_*` on fresh builds by adjusting its logic if desired (similar to Lane A).

**Handling dynamic legacy name:** B8 uses `employees_legacy_{YYYYMMDD}` at run time. Tenant_demo has `employees_legacy_20260305`; other tenants may have different suffixes. Options:

- Query `pg_tables` for `tablename LIKE 'employees_legacy_%'` and drop each match.
- Use `DROP TABLE IF EXISTS employees_legacy_20260305 CASCADE` only if all tenants use the same date (risky).
- Prefer: `SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'employees_legacy_%'` then `DROP TABLE IF EXISTS <each> CASCADE`.

### Option B: Migrate then drop

If any tenant has non-empty `employees_legacy_*` or `employee_roles`:

1. Migrate data into `people` and `person_roles` (with role mapping).
2. Optionally create `driver_profiles` where the role implies driver.
3. After backfill, apply the drop steps from Option A.

Given tenant_demo and the lineage analyzed, both tables are empty, so Option B is not needed for current data.

---

## Summary

| Table | Rows | Classification | Action |
|-------|------|----------------|--------|
| employees_legacy_20260305 | 0 | SAFE TO DROP NOW | Drop after employee_roles |
| employee_roles | 0 | SAFE TO DROP NOW | Drop first (remove FK) |

**Recommendation:** Treat Lane B as drop-only: add a tenant migration to drop `employee_roles` (after dropping its FK) and `employees_legacy_*`, then remove the `/api/v1/employees` router and `EmployeeRole` (and optionally `Employee`) from the codebase.
