# Tenant provisioning failure — forensic report

> **Document type:** Forensic / historical analysis — **not** the canonical production operator runbook.  
> **Tenant migrations (operators):** use `scripts/tenant_upgrade_head.sh` in `truckerp-api` with `ALEMBIC_TENANT_DATABASE_URL` set (see `docs/secrets.md`, `.cursor/rules/tenant-migrations.mdc`).  
> Any raw `alembic -c alembic_tenant.ini …` snippets below are **legacy context, one-off repair discussion, or non-operator** — not the default prod upgrade path.

**Error:** `UndefinedColumnError: column "is_primary" of relation "person_roles" does not exist`

**Observed state:** Tenant `attia` — `status=PENDING_SETUP`, `db_status=ERROR`, `db_name=tenant_attia`. Tenant DB `tenant_erp`: no `person*` tables.

---

## 1. Provisioning code expectations

### Tenant provisioning service

- **File:** `app/services/tenant_provisioning.py`
- **Flow:** `provision_tenant_db()` → `_create_database_if_not_exists()` → `_run_tenant_migrations(tenant_db_url, settings.tenant_alembic_target_rev)` → `validate_tenant_schema_strict(tenant_db_url)` → `_seed_tenant_creator(...)`.

### Signup flow creating OWNER role

- **File:** `app/services/tenant_provisioning.py`, `_seed_tenant_creator()` (lines 171–216).
- **SQL executed:** Inserts into `people` then into `person_roles` with columns: `tenant_id`, `person_id`, `role_code`, **`is_primary`**, `is_active`, `created_at`, **`updated_at`** (see lines 211–214).

### SQLAlchemy models

- **File:** `app/models/person.py`
  - **Person:** `__tablename__ = "people"` — columns include `tenant_id`, `platform_user_id`, `is_active`, `first_name`, `last_name`, `email`, etc., `created_at`, `updated_at`.
  - **PersonRole:** `__tablename__ = "person_roles"` — columns: `id`, `tenant_id`, `person_id`, `role_code`, **`is_primary`**, `is_active`, `created_at`, **`updated_at`** (lines 61–75).
- **Schema validation:** `app/services/tenant_schema_validation.py` (lines 60–72) requires `person_roles` to have: `id`, `tenant_id`, `person_id`, `role_code`, **`is_primary`**, `is_active`, `created_at`, **`updated_at`**.

### Which tables provisioning expects

- `people`, `person_roles`, `driver_profiles`, `driver_onboarding_submissions`, `tenants` (and others). For the OWNER seed it only writes to `people` and `person_roles`.

### Required columns (especially `is_primary`)

- **person_roles:** `tenant_id`, `person_id`, `role_code`, **`is_primary`**, `is_active`, `created_at`, **`updated_at`**.

### Required migrations that should create them

- Tenant Alembic config: **`alembic_tenant.ini`** (script_location: `alembic_tenant/versions/`).
- People/roles tables are introduced in the chain that includes **74ff8253c43c** and **ea59a17db8a3**. The **model and provisioning code** expect `person_roles` to include `is_primary` and `updated_at`; the migration that actually creates the table in the **executed** path does not add them (see below).

---

## 2. Tenant Alembic migration chain truth

### Current HEAD

- **Single head:** `cb313448b94e` (from `alembic -c alembic_tenant.ini heads`).
- **Relevant lineage:**  
  `... → fefd8f1df8d9 → 74ff8253c43c → ea59a17db8a3 → f01a9b2c3d4e → a5b6c7d8e9f0 → cb313448b94e`.

### Which migration creates `person_roles` / `is_primary`

| Revision            | Creates `person_roles`? | Has `is_primary`? | Has `updated_at`? |
|---------------------|-------------------------|--------------------|--------------------|
| **74ff8253c43c**    | **Yes** (if table missing) | **No**             | **No**             |
| **ea59a17db8a3**    | Yes (only if table missing) | Yes                | Yes                |

- **74ff8253c43c** (`74ff8253c43c_people_foundation_people_driver_.py`):  
  Creates `person_roles` with: `id`, `tenant_id`, `person_id`, `role_code`, `is_active`, `created_at` only (lines 55–64). **No `is_primary`, no `updated_at`.**
- **ea59a17db8a3** (`ea59a17db8a3_people_foundation_people_roles_driver_.py`):  
  `if "person_roles" not in tables:` then creates `person_roles` with `is_primary` and `updated_at` (lines 55–72).  
  Because **74ff runs first**, `person_roles` **already exists** when ea59a17db8a3 runs, so ea59a17db8a3 **never creates the table** and never adds `is_primary` or `updated_at`.

### People-first migration: exists but does not fix existing tables

- The “full” people/roles schema (with `is_primary`, `updated_at`) is in **ea59a17db8a3**, which is **idempotent** and only creates tables **if missing**. It does not alter an existing `person_roles` table created by 74ff. So:
  - **Expected tenant schema (model + provisioning):** `person_roles` has `is_primary`, `updated_at`.
  - **Actual tenant migrations:** 74ff creates `person_roles` without those columns; ea59a17db8a3 skips creation.
  - **Diff:** Existing tenant DBs that ran the chain have `person_roles` **missing** `is_primary` and `updated_at`.

### Summary

- **EXPECTED:** `person_roles` with `id`, `tenant_id`, `person_id`, `role_code`, `is_primary`, `is_active`, `created_at`, `updated_at`.
- **ACTUAL (from 74ff):** `person_roles` with `id`, `tenant_id`, `person_id`, `role_code`, `is_active`, `created_at` only.
- **DIFF:** Missing columns: **`is_primary`**, **`updated_at`**.

---

## 3. Root cause classification

**Chosen:** **Partial / conflicting migrations (earlier migration creates table with subset of columns; later migration would create full table but skips because table exists).**

- **74ff8253c43c** creates `person_roles` without `is_primary` and without `updated_at`.
- **ea59a17db8a3** would create the full table but runs `if "person_roles" not in tables:` and skips when 74ff has already created it.
- Migrations **are** executed during provisioning (`_run_tenant_migrations(..., "head")`); the failure is due to **schema content**, not “migration not executed” or “wrong config.” Model and code expect columns that no migration adds to an existing 74ff-created table.

---

## 4. Minimal safe fix

### A. Code change

- **No application code change required.** Model (`app/models/person.py`) and provisioning (`app/services/tenant_provisioning.py`) and schema validation (`app/services/tenant_schema_validation.py`) are correct; the deficit is in the tenant DB schema created by migrations.

### B. Alembic migration (required)

- **Add one new tenant migration** after current head `cb313448b94e` that:
  - Adds `is_primary` to `person_roles` if missing (NOT NULL, default false).
  - Adds `updated_at` to `person_roles` if missing (TIMESTAMP WITH TIME ZONE, default now(), NOT NULL).
- **Idempotent:** use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (or inspect and add only when column absent) so existing broken DBs and future DBs both end up correct.

**New migration file (full):**

- **Path:** `alembic_tenant/versions/<new_revision>_person_roles_add_is_primary_updated_at.py`
- **revision:** e.g. `dd4c89b0a848` (or generate via `alembic revision`).
- **down_revision:** `cb313448b94e`
- **upgrade():**
  - If `person_roles` exists and column `is_primary` does not exist → `op.add_column("person_roles", sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")), schema="public")`.
  - If `person_roles` exists and column `updated_at` does not exist → `op.add_column("person_roles", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True), schema="public")` then `op.execute("UPDATE person_roles SET updated_at = created_at WHERE updated_at IS NULL")` and `op.alter_column("person_roles", "updated_at", nullable=False, server_default=sa.text("now()"), schema="public")` (or equivalent).
- **downgrade():** Optional; can drop the added columns only if they were added by this migration (complex to track). Safer: leave downgrade no-op or drop columns only when safe.

### C. Existing DB repair steps (idempotent, safe)

Run against **each** affected tenant DB (e.g. `tenant_erp`, `tenant_attia`, and any other tenant that has or will have `person_roles`):

1. **Ensure migrations are at head** (so `person_roles` exists; for DBs like `tenant_erp` with no `person_*` tables, this creates them via 74ff, then the new migration will add columns). **Non-operator / historical repair snippet** (today use `bash scripts/tenant_upgrade_head.sh` with env set instead):

   ```bash
   # Set ALEMBIC_TENANT_DATABASE_URL to point at the tenant DB, then:
   cd /app && alembic -c alembic_tenant.ini upgrade head
   ```

2. **Add missing columns if present** (idempotent; safe to run multiple times):

   ```sql
   -- For tenant_attia, tenant_erp, or any tenant DB
   ALTER TABLE person_roles ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;
   ALTER TABLE person_roles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE;
   UPDATE person_roles SET updated_at = created_at WHERE updated_at IS NULL;
   ALTER TABLE person_roles ALTER COLUMN updated_at SET NOT NULL;
   ALTER TABLE person_roles ALTER COLUMN updated_at SET DEFAULT now();
   ```

   (If your Postgres version does not support `ADD COLUMN IF NOT EXISTS`, use a DO block or check `information_schema.columns` first.)

**Concrete commands (example for tenant_attia):**

```bash
# From host, using db_run.sh or equivalent to load env and run psql against tenant DB
./scripts/db_run.sh "psql -h <host> -U <user> -d tenant_attia -c \"
  ALTER TABLE person_roles ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;
  ALTER TABLE person_roles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE;
  UPDATE person_roles SET updated_at = created_at WHERE updated_at IS NULL;
  ALTER TABLE person_roles ALTER COLUMN updated_at SET NOT NULL;
  ALTER TABLE person_roles ALTER COLUMN updated_at SET DEFAULT now();
\""
```

Repeat for `tenant_erp` and any other tenant DBs. For `tenant_erp` (no `person_*` tables yet), run a **full tenant upgrade to head** (operator: `tenant_upgrade_head.sh`) first so 74ff creates the tables, then run the new migration (or the same ALTERs) so `person_roles` gets `is_primary` and `updated_at`.

**Existing script:** `scripts/fix_tenant_schema.sh` already adds `is_primary` for a given tenant DB; extend it to also add `updated_at` to `person_roles` when missing, so one script fixes both columns.

---

## 5. Safety verification

### Exact commands to verify

1. **Provisioning succeeds (new tenant)**  
   Create a new tenant (signup or admin flow) and confirm:
   - `provision_tenant_db()` completes without error.
   - Tenant has `db_status=READY` and no `UndefinedColumnError`.

2. **OWNER role inserted**  
   For the new (or repaired) tenant DB:
   ```sql
   SELECT * FROM person_roles WHERE role_code = 'OWNER';
   ```
   Should return at least one row with `is_primary = true`.

3. **person_roles.is_primary exists**  
   ```sql
   SELECT column_name FROM information_schema.columns
   WHERE table_name = 'person_roles' AND column_name IN ('is_primary', 'updated_at');
   ```
   Should return both `is_primary` and `updated_at`.

4. **No schema drift**  
   Run tenant schema validation (e.g. from app or script):
   ```bash
   # With ALEMBIC_TENANT_DATABASE_URL or TENANT_DATABASE_URL set to tenant DB
   python -c "
   from app.services.tenant_schema_validation import validate_tenant_schema_strict
   import os
   url = os.environ['ALEMBIC_TENANT_DATABASE_URL']  # or build from POSTGRES_* + db_name
   validate_tenant_schema_strict(url)  # raises if invalid
   print('OK')
   "
   ```
   Should complete without exception.

---

## Output summary (strict)

**ROOT CAUSE**  
74ff8253c43c creates `person_roles` without `is_primary` and without `updated_at`. ea59a17db8a3 would create the full table but only when `person_roles` does not exist; because 74ff runs first, ea59a17db8a3 never runs its create and never adds those columns. Provisioning and the model expect `is_primary` and `updated_at` → UndefinedColumnError when inserting OWNER.

**EVIDENCE**  
- `app/services/tenant_provisioning.py` lines 211–214: INSERT into `person_roles` includes `is_primary`, `updated_at`.  
- `app/models/person.py` lines 69, 74–75: PersonRole defines `is_primary`, `updated_at`.  
- `alembic_tenant/versions/74ff8253c43c_*.py` lines 55–64: creates `person_roles` with no `is_primary`, no `updated_at`.  
- `alembic_tenant/versions/ea59a17db8a3_*.py` lines 55–56: `if "person_roles" not in tables:` → creation (with is_primary/updated_at) is skipped when table already exists.

**MINIMAL FIX**  
1. New tenant migration after `cb313448b94e`: add `is_primary` and `updated_at` to `person_roles` when missing (idempotent).  
2. No application code change.

**DB REPAIR COMMANDS**  
- **Lab / repair context (this report):** run `alembic -c alembic_tenant.ini upgrade head` for each affected tenant DB (so `person_roles` exists and new migration runs). **Operators:** prefer `bash scripts/tenant_upgrade_head.sh` with `ALEMBIC_TENANT_DATABASE_URL` per `docs/secrets.md`.  
- Or run the ALTERs above (ADD COLUMN IF NOT EXISTS for `is_primary` and `updated_at`, then backfill and set NOT NULL/DEFAULT for `updated_at`) per tenant DB.  
- Extend `scripts/fix_tenant_schema.sh` to add `updated_at` in addition to `is_primary`.

**VERIFICATION STEPS**  
- New tenant provisioning completes; `person_roles` has OWNER row with `is_primary = true`; `information_schema` shows `is_primary` and `updated_at`; `validate_tenant_schema_strict(tenant_db_url)` passes.
