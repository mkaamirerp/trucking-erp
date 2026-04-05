# Alembic platform handoff: what happened, what we fixed, what to remember

This doc records a production fix so future work (and agents) don’t repeat the same mistakes.

---

## Root cause

We were trying to migrate **platform** tables (`platform_onboarding_payloads`, `platform_otp_tokens`) using the **wrong** Alembic config:

| | Wrong | Correct |
|---|--------|--------|
| Config | `alembic.ini` | `alembic_platform.ini` |
| Script location | `/app/alembic/versions` | `/app/alembic_platform/versions` |
| Contains 0015–0018 | No | Yes (0013–0018) |

Because of that, platform migrations never ran → columns like `platform_onboarding_payloads.status` were missing → the cleanup script failed.

---

## Second blocker

Platform DB migration failed at **0016** because:

- `alembic_version.version_num` was `VARCHAR(32)`
- Revision id `0016_onboarding_payload_tenant_id_nullable` is longer than 32 characters

Postgres threw: **value too long for type character varying(32)**.

### Fix applied

Expand the column length:

```sql
ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255);
```

Then run platform migrations with the **correct** config (see below).

---

## Fix applied (authoritative)

1. **Expand `alembic_version` length** (on the **platform** DB):
   ```sql
   ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255);
   ```

2. **Run platform migrations using the correct config:**
   ```bash
   alembic -c alembic_platform.ini upgrade head
   ```

   This successfully applied:
   - 0016_onboarding_payload_tenant_id_nullable
   - 0017_otp_signup_refinements
   - 0018_onboarding_public_id_uuid

3. **Cleanup script** now runs (e.g. dry-run):
   ```bash
   python -m app.scripts.cleanup_onboarding
   ```
   Output: `Done. OTP: 0, Drafts: 0`

---

## Permanent rule (do not forget)

- **Platform DB migrations** MUST always use: **`alembic_platform.ini`**
- **Tenant DB schema** is driven by **`alembic_tenant.ini`** + `alembic_tenant/versions/` (config/source-of-truth for revisions).
- **Tenant DB operator upgrades** (prod / routine) MUST go through **`scripts/tenant_upgrade_head.sh`** inside `truckerp-api` at `/app` so **preflight** runs before `upgrade head`. Do **not** use raw `alembic -c alembic_tenant.ini upgrade head` as the default operator path—it skips preflight (see `.cursor/rules/tenant-migrations.mdc` and `docs/secrets.md`).
- **Do not** use root **`alembic.ini`** for platform schema changes.

---

## Commands we used (working)

**Run platform migrations** (container, env from secrets):

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_platform.ini upgrade head'
```

**Run tenant migrations (operator — canonical):** `ALEMBIC_TENANT_DATABASE_URL` must point at the target tenant DB (async URL). Example via host wrapper:

```bash
cd /home/admin/trucking_erp
./scripts/db_run.sh bash -c 'export ALEMBIC_TENANT_DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@truckerp-postgres:5432/tenant_demo" && bash scripts/tenant_upgrade_head.sh'
```

(Fleet-wide: `python -m app.scripts.tenant_fleet_upgrade_head` in the same container env; see `docs/secrets.md`.)

**Run cleanup (dry-run):**

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.cleanup_onboarding'
```

---

That’s what Cursor (and any agent) needs to remember. See also `.cursor/rules/alembic-platform-tenant-config.mdc` for the injected rule.
