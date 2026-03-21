# Tenant Demo Legacy Tables — Alembic Anti-Regression Report & Permanent Cleanup Plan

## 1. Alembic Anti-Regression Report

### users

| Question | Answer |
|----------|--------|
| **Which migration originally created it?** | `c8a3d0b9c777_add_tenants_and_rbac.py` (via `ensure_users_table()`) |
| **Later migration replaced/superseded?** | No. `fefd8f1df8d9` dropped `fk_users_tenant_id` only; table remains. |
| **Fresh `upgrade head` still creates it?** | **YES** — c8a3d0b9c777 is in the lineage and runs before head. |
| **SQLAlchemy metadata contains it?** | **NO** — no `User` model; auth uses `PlatformUser` (platform DB). |
| **Autogenerate would recreate after drop?** | **NO** — metadata has no `users` table. |
| **Exact file(s)** | `alembic_tenant/versions/c8a3d0b9c777_add_tenants_and_rbac.py` (lines 357–411) |

---

### user_roles

| Question | Answer |
|----------|--------|
| **Which migration originally created it?** | `c8a3d0b9c777_add_tenants_and_rbac.py` |
| **Later migration replaced/superseded?** | No. Dropped only in c8a3d0b9c777’s **downgrade**, not in any upgrade. |
| **Fresh `upgrade head` still creates it?** | **YES** |
| **SQLAlchemy metadata contains it?** | **NO** — no `UserRole` model. |
| **Autogenerate would recreate after drop?** | **NO** |
| **Exact file(s)** | `alembic_tenant/versions/c8a3d0b9c777_add_tenants_and_rbac.py` (lines 557–585) |

---

### driver_phones_old

| Question | Answer |
|----------|--------|
| **Which migration originally created it?** | `7de1d90c39eb_add_driver_phones.py` — created by **rename** (`driver_phones` → `driver_phones_old`) when upgrading from a DB that already had `driver_phones`. |
| **Later migration replaced/superseded?** | No. Downgrade of 7de1d90c39eb renames `driver_phones_old` back to `driver_phones`. |
| **Fresh `upgrade head` still creates it?** | **NO** — on a fresh empty DB, `driver_phones` does not exist, so the migration creates `driver_phones` directly and never creates `driver_phones_old`. |
| **SQLAlchemy metadata contains it?** | **NO** — only `driver_phones` (DriverPhone model). |
| **Autogenerate would recreate after drop?** | **NO** |
| **Exact file(s)** | `alembic_tenant/versions/7de1d90c39eb_add_driver_phones.py` (lines 26–34 upgrade, 59–62 downgrade) |

**Note:** `driver_phones_old` exists only in DBs that were upgraded from a pre-7de1d90c39eb state. Fresh installs never get it.

---

### employees_legacy_20260305

| Question | Answer |
|----------|--------|
| **Which migration originally created it?** | `b8f9cfe34f1b_b8_payroll_and_settlements.py` — created by **rename** (`employees` → `employees_legacy_YYYYMMDD`) when `employees` existed. The date is from `datetime.utcnow()` at migration run time. |
| **Later migration replaced/superseded?** | No. |
| **Fresh `upgrade head` still creates it?** | **YES** — 5c9de38d8b3e creates `employees`, then b8f9cfe34f1b renames it to `employees_legacy_YYYYMMDD` (date at run time). |
| **SQLAlchemy metadata contains it?** | **NO** — `Employee` model uses `__tablename__ = "employees"` (the new payee-backed table from b8), not the legacy one. |
| **Autogenerate would recreate after drop?** | **NO** |
| **Exact file(s)** | `alembic_tenant/versions/b8f9cfe34f1b_b8_payroll_and_settlements.py` (lines 115–118), `alembic_tenant/versions/5c9de38d8b3e_add_employees_and_roles.py` (creates original `employees`) |

**Blocking dependency:** `employee_roles.employee_id` → `employees_legacy_20260305.id` (FK). Must resolve before drop.

---

### tenants

| Question | Answer |
|----------|--------|
| **Which migration originally created it?** | `c8a3d0b9c777_add_tenants_and_rbac.py` (and seeded with INSERT). |
| **Later migration replaced/superseded?** | No. `fefd8f1df8d9` dropped FKs **to** `tenants` from other tables; `f01a9b2c3d4e` dropped tenant_id FKs from people/roles/profiles. `tenants` table itself was never dropped. |
| **Fresh `upgrade head` still creates it?** | **YES** |
| **SQLAlchemy metadata contains it?** | **YES** — `app.models.tenant.models.Tenant`, `__tablename__ = "tenants"`. |
| **Autogenerate would recreate after drop?** | **YES** — metadata includes Tenant model. |
| **Exact file(s)** | `alembic_tenant/versions/c8a3d0b9c777_add_tenants_and_rbac.py` (lines 464–479, 741–742 downgrade), `app/models/tenant/models.py` |

**Current DB state:** No FKs currently reference `tenants` (fefd8f1df8d9 and f01a9b2c3d4e removed them). But many models still declare `ForeignKey("tenants.id")` on `tenant_id` columns (loads, drivers, broker, truck, payroll, payee, driver_document, driver_phone, driver_onboarding_submission, employee_role). Those FKs are not present in the DB; models are out of sync with DB.

---

### drivers

| Question | Answer |
|----------|--------|
| **Which migration originally created it?** | `a59de96e634e_create_drivers_table.py` (base of lineage). |
| **Later migration replaced/superseded?** | No. Many migrations add columns/constraints (person_id, payee_id, license fields); none drop the table. |
| **Fresh `upgrade head` still creates it?** | **YES** |
| **SQLAlchemy metadata contains it?** | **YES** — `app.models.driver.Driver`. |
| **Autogenerate would recreate after drop?** | **YES** |
| **Exact file(s)** | `alembic_tenant/versions/a59de96e634e_create_drivers_table.py`, `app/models/driver.py` |

---

## 2. tenants — Intentional or Transitional?

**Conclusion: Transitional compatibility table; elimination is possible later.**

### Current role

- `tenants` in the tenant DB was the original tenant registry before platform architecture.
- Platform DB has `platform_tenants`; each tenant has its own tenant DB (e.g. `tenant_demo`).
- `fefd8f1df8d9` and `f01a9b2c3d4e` removed FKs from tenant tables to `tenants` to avoid cross-DB coupling and redundancy.
- **At present, no DB FKs reference `tenants`.** The table exists with 1 row (demo tenant) but nothing enforces referential integrity to it.

### Why it’s still there

- `tenant_schema_validation.py` lists `tenants` as required.
- `Tenant` model exists and is used (e.g. for schema checks).
- c8a3d0b9c777 seeds it and some logic may still depend on its presence.

### Migration path to remove `tenants`

1. **Remove `ForeignKey("tenants.id")` from all models**  
   Change `tenant_id` from `ForeignKey("tenants.id")` to plain `Integer` (or `BigInteger` where applicable) in: Load, Driver, Broker, Truck, DriverPhone, DriverDocument, DriverDocumentFile, DriverOnboardingSubmission, EmployeeRole, and all payee/payroll models. Keep `tenant_id` columns for isolation; drop only the FK definition.

2. **Update `tenant_schema_validation`**  
   Remove `tenants` from required tables (or make it optional).

3. **Add migration to drop `tenants`**  
   After model changes, add a tenant migration that does `DROP TABLE tenants CASCADE` (or equivalent).

4. **Remove or adapt `Tenant` model**  
   Either delete it or repurpose it for platform-only use if needed elsewhere.

This can be done only after all FK references and validation checks are updated. **Do not drop `tenants` in Lane A.**

---

## 3. Implementation Plan

### Lane A — Safe removals (migration only)

Create one tenant Alembic migration that runs **after** current head (`e5f6a7b8c9d0`).

**Exact steps (idempotent):**

1. `ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_actor_user_id_fkey;`
2. `DROP TABLE IF EXISTS user_roles CASCADE;`
3. `DROP TABLE IF EXISTS users CASCADE;`
4. `DROP TABLE IF EXISTS driver_phones_old CASCADE;`

Order matters: drop `user_roles` before `users` (user_roles has FK to users).

**Code changes for Lane A:** None. Only a new Alembic migration.

**Migration template (idempotent):**
```python
def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # 1. Drop audit_log FK to users (must precede users drop)
    if insp.has_table("audit_log"):
        fks = {fk["name"]: fk for fk in insp.get_foreign_keys("audit_log")}
        if "audit_log_actor_user_id_fkey" in fks:
            op.drop_constraint("audit_log_actor_user_id_fkey", "audit_log", type_="foreignkey")
    # 2. Drop tables (order: user_roles first, then users)
    op.execute("DROP TABLE IF EXISTS user_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS driver_phones_old CASCADE")

def downgrade() -> None:
    # No downgrade - these tables are legacy; do not recreate
    pass
```

Use `op.execute("DROP TABLE IF EXISTS ...")` for idempotency. The audit_log constraint check ensures we don't fail if it was already dropped.

---

### Lane B — Blocked legacy resolution

**`employees_legacy_20260305`**

- Blocked by `employee_roles.employee_id` → `employees_legacy_20260305.id`.
- `EmployeeRole` exists and is used by `app/routers/employees.py`.
- `EmployeeRole.employee_id` in the model uses `ForeignKey("employees.id")` — but the DB FK points at `employees_legacy_20260305` because b8 renamed `employees` and did not update `employee_roles`.

Options:

1. **Drop `employee_roles` and `employees_legacy_20260305`**  
   If the legacy Employee/EmployeeRole flow is deprecated and `/employees` is unused or will be removed.

2. **Point `employee_roles` at new `employees`**  
   If the payee-backed `Employee` table is the source of truth, add a migration to:
   - drop `employee_roles.employee_id` FK to `employees_legacy_20260305`;
   - add FK to `employees` (or the correct new table);
   - backfill/migrate any required data;
   - then drop `employees_legacy_20260305`.

**Next step:** Confirm whether `employee_roles` / employees router is still in use and which option to take. Do **not** drop `employees_legacy_20260305` until this is resolved.

---

## 4. Verification Proof Requirements

After implementing Lane A migration:

### 4.1 Upgrade on current tenant_demo

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh'
```

**Expected:** Migration runs; `users`, `user_roles`, `driver_phones_old` no longer exist.

**Proof:**
```sql
SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('users','user_roles','driver_phones_old');
```
→ 0 rows.

---

### 4.2 Fresh empty tenant DB → upgrade head

1. Create a new empty tenant DB (e.g. `tenant_test`).
2. Run `alembic -c alembic_tenant.ini upgrade head` with `ALEMBIC_TENANT_DATABASE_URL` pointing at that DB.
3. Confirm `users`, `user_roles`, `driver_phones_old` are **not** created (Lane A migration drops them if a prior migration created them; on a fresh DB, only `users` and `user_roles` would have been created by c8a3d0b9c777; `driver_phones_old` would not exist).
4. After upgrade, verify dropped tables are absent.

---

### 4.3 Dropped tables do not come back

- Re-run `upgrade head` on the same DB.
- Idempotent migrations (e.g. `DROP TABLE IF EXISTS`) should not fail.
- Confirm tables remain dropped.

---

### 4.4 Autogenerate does not re-add dropped tables

```bash
alembic -c alembic_tenant.ini revision --autogenerate -m "test_no_recreate"
```

**Expected:** Autogenerate should **not** suggest recreating `users`, `user_roles`, or `driver_phones_old` (they are not in SQLAlchemy metadata).

**Note:** If autogenerate proposes any of these, the metadata or model imports must still expose them; fix that before relying on the migration.

---

## 5. Summary Table

| Table | Created by | Fresh upgrade creates? | In metadata? | Autogenerate recreates? | Lane |
|-------|------------|------------------------|--------------|------------------------|------|
| users | c8a3d0b9c777 | YES | NO | NO | A |
| user_roles | c8a3d0b9c777 | YES | NO | NO | A |
| driver_phones_old | 7de1d90c39eb (rename) | NO | NO | NO | A |
| employees_legacy_* | b8f9cfe34f1b (rename) | YES | NO | NO | B (blocked) |
| tenants | c8a3d0b9c777 | YES | YES | YES | Keep |
| drivers | a59de96e634e | YES | YES | YES | Keep |
