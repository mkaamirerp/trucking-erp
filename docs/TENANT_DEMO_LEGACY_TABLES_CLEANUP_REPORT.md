# Tenant Demo Legacy Tables — Dependency & Usage Safety Report

## 1. Per-Table Analysis

### tenants

| Attribute | Details |
|-----------|---------|
| **Row count** | 1 |
| **FKs TO this table** | Many: loads, drivers, broker, trucks, driver_documents, driver_document_files, driver_onboarding_submissions, employee_roles, payees, pay_periods, pay_profiles, pay_entries, pay_runs, pay_run_items, compensation_profiles, etc. (via `tenant_id` columns) |
| **FKs FROM this table** | None |
| **Indexes** | `tenants_pkey`, `uq_tenants_slug`, `ix_tenants_slug` |
| **Views** | None |
| **Functions/triggers** | None (only RI triggers) |
| **Backend code** | **ACTIVELY USED**: `app/models/tenant/models.py` — `Tenant` model, `__tablename__ = "tenants"`. Many models reference `ForeignKey("tenants.id")`: loads, drivers, broker, truck, payee, payroll, driver_document, driver_phone, driver_onboarding_submission, employee_role. |
| ** tenant_schema_validation** | Lists `tenants` in required_tables |
| **Migrations** | `c8a3d0b9c777_add_tenants_and_rbac.py` creates it; `fefd8f1df8d9` dropped some tenant_id FKs. Many migrations still create FKs to `tenants.id`. |
| **Tests** | No direct references |

**Note:** The migration `fefd8f1df8d9_drop_tenant_id_fks_to_tenants_in_tenant_` dropped some FK constraints (e.g. `fk_drivers_tenant_id`, `fk_users_tenant_id`), but many tables still have `tenant_id` columns and/or FKs to `tenants.id` (e.g. loads, drivers, payroll tables, broker, truck, employee_roles).

**Classification: KEEP TEMPORARILY** — `tenants` is the FK target for `tenant_id` across the tenant DB. It is not legacy residue; it is the local tenant registry. Dropping it would break loads, drivers, payroll, etc. A future migration could remove tenant_id FKs and the tenants table only after a full people-first / single-tenant-per-DB schema redesign.

---

### users

| Attribute | Details |
|-----------|---------|
| **Row count** | 0 |
| **FKs TO this table** | `audit_log.actor_user_id` → `users.id`, `user_roles.user_id` → `users.id` |
| **FKs FROM this table** | `users.tenant_id` → `tenants.id` (if still present) |
| **Indexes** | `users_pkey`, `ix_users_tenant_id`, `uq_users_email` |
| **Views** | None |
| **Functions/triggers** | RI triggers for FKs |
| **Backend code** | **NOT USED** — Auth uses `PlatformUser` (platform DB). No model with `__tablename__ = "users"` in app. |
| **Migrations** | `c8a3d0b9c777` creates users; `fefd8f1df8d9` drops `fk_users_tenant_id`. |
| **Tests** | No references |

**Classification: SAFE TO DROP NOW** — No backend code references it. Must drop `user_roles` first (references users), then `audit_log` FK or set `actor_user_id` nullable/drop FK, then `users`.

---

### user_roles

| Attribute | Details |
|-----------|---------|
| **Row count** | 0 |
| **FKs TO this table** | None |
| **FKs FROM this table** | `user_roles.user_id` → `users.id`, `user_roles.role_id` → `roles.id` |
| **Indexes** | `user_roles_pkey`, `ix_user_roles_user_id`, `ix_user_roles_role_id`, `uq_user_roles_user_role` |
| **Views** | None |
| **Functions/triggers** | RI triggers |
| **Backend code** | **NOT USED** — RBAC now via `PlatformTenantMember` / `TenantMembership`. |
| **Migrations** | `c8a3d0b9c777` creates user_roles. |
| **Tests** | No references |

**Classification: SAFE TO DROP NOW** — Drop before `users` (user_roles references users). Order: drop `user_roles` first, then `users`.

---

### driver_phones_old

| Attribute | Details |
|-----------|---------|
| **Row count** | 0 |
| **FKs TO this table** | None |
| **FKs FROM this table** | `driver_phones_old.driver_id` → `drivers.id` |
| **Indexes** | `driver_phones_pkey`, `uq_driver_phone_dedupe`, `ix_driver_phones_driver_id`, `ix_driver_phones_phone_number`, `ux_driver_primary_phone` |
| **Views** | None |
| **Functions/triggers** | RI triggers |
| **Backend code** | **NOT USED** — `DriverPhone` model uses `driver_phones`. Created during driver_phones migration rename. |
| **Migrations** | `7de1d90c39eb_add_driver_phones.py` renames driver_phones → driver_phones_old when creating new driver_phones. |
| **Tests** | No references |

**Classification: SAFE TO DROP NOW** — Backup table from migration; nothing references it.

---

### employees_legacy_20260305

| Attribute | Details |
|-----------|---------|
| **Row count** | 0 |
| **FKs TO this table** | `employee_roles.employee_id` → `employees_legacy_20260305.id` |
| **FKs FROM this table** | None |
| **Indexes** | `employees_pkey`, `ix_employees_tenant_code`, `ix_employees_tenant_id`, `ix_employees_email` |
| **Views** | None |
| **Functions/triggers** | RI triggers |
| **Backend code** | **NOT USED** — `Employee` model uses `__tablename__ = "employees"` (different table). `EmployeeRole` has `ForeignKey("employees.id")` in code, but DB FK is `employee_roles_employee_id_fkey` → `employees_legacy_20260305`. There is no `employees` table; only `employees_legacy_20260305`. Employee router would fail on Employee model (queries non-existent `employees`). |
| **Migrations** | Legacy backup from 2026-03-05. |
| **Tests** | No references |

**Classification: DROP AFTER CODE CLEANUP** — `employee_roles` references this table. Before dropping: (1) Migrate `employee_roles` to reference `payees`/new employees schema if Employee flow is still used, or (2) Drop `employee_roles` and then `employees_legacy_20260305`. If Employee/EmployeeRole is deprecated, drop `employee_roles` first, then `employees_legacy_20260305`.

---

### drivers

| Attribute | Details |
|-----------|---------|
| **Row count** | 6 |
| **FKs TO this table** | `driver_documents.driver_id`, `driver_phones.driver_id`, `driver_phones_old.driver_id`, `loads.driver_id`, `pay_entries.driver_id`, `pay_profiles.driver_id`, `pay_run_items.driver_id` |
| **FKs FROM this table** | `drivers` → `people (tenant_id, person_id)` (composite FK) |
| **Indexes** | `drivers_pkey`, `ix_drivers_tenant_id`, `ix_drivers_person_id`, `ix_drivers_license_expiry_date`, `uq_drivers_payee_id` |
| **Views** | None |
| **Functions/triggers** | RI triggers |
| **Backend code** | **ACTIVELY USED** — `app/models/driver.py` (Driver model), `drivers` router, `dashboard`, `loads`, `payroll`, `pay_runs`, etc. |
| **Migrations** | Multiple (create, person_id, payee_id, license fields). |
| **Tests** | No direct references |

**Classification: KEEP TEMPORARILY** — Core table; people-first transition will migrate away from it. Do not drop.

---

## 2. Summary Classification

| Table | Classification | Reason |
|-------|----------------|--------|
| **tenants** | KEEP TEMPORARILY | FK target for tenant_id; actively used. |
| **users** | SAFE TO DROP NOW | No backend use; 0 rows. Drop after user_roles. |
| **user_roles** | SAFE TO DROP NOW | No backend use; 0 rows. Drop first. |
| **driver_phones_old** | SAFE TO DROP NOW | Migration backup; 0 rows; nothing references it. |
| **employees_legacy_20260305** | DROP AFTER CODE CLEANUP | employee_roles references it. Drop employee_roles first, or migrate employee_roles. |
| **drivers** | KEEP TEMPORARILY | Actively used; 6 rows. |

---

## 3. DROP Plan (Safe Tables Only)

Execute in this order on `tenant_demo`:

```sql
-- 1. Drop user_roles first (references users)
DROP TABLE IF EXISTS user_roles CASCADE;

-- 2. Drop audit_log FK to users (or drop audit_log if unused)
-- Check: does audit_log have rows? If so, set actor_user_id = NULL or drop the FK.
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_actor_user_id_fkey;

-- 3. Drop users
DROP TABLE IF EXISTS users CASCADE;

-- 4. Drop driver_phones_old
DROP TABLE IF EXISTS driver_phones_old CASCADE;
```

**Do NOT drop:** tenants, drivers, employees_legacy_20260305 (until employee_roles is dropped or migrated).

---

## 4. Pre-Flight Checks Before Running DROP

```sql
-- Confirm zero rows
SELECT (SELECT COUNT(*) FROM user_roles) AS user_roles, (SELECT COUNT(*) FROM users) AS users, (SELECT COUNT(*) FROM driver_phones_old) AS driver_phones_old;

-- Confirm audit_log FK exists
SELECT conname FROM pg_constraint WHERE conrelid = 'audit_log'::regclass AND contype = 'f' AND conname LIKE '%actor_user%';
```

---

## 5. employees_legacy_20260305 — Deferred Plan

To drop `employees_legacy_20260305` later:

1. **Option A:** Drop `employee_roles` (if EmployeeRole flow is deprecated), then `employees_legacy_20260305`.
2. **Option B:** If Employee/EmployeeRole is still used, migrate `employee_roles.employee_id` to point at the new `employees`/payee-backed schema, then drop `employees_legacy_20260305`.

**Note:** The `Employee` model expects table `employees`, which does not exist. The active employee table appears to be `employees_legacy_20260305`. The employees router may be broken or using a different code path; verify before dropping.
