# Alembic Root Tree Status

## Current status (do not assume deletion-ready)

Root `alembic/` and root `alembic.ini` are still required **today** by CI/scripts/audit.
They are not the normal runtime migration path, but they are still part of repository safety checks.

## Runtime migration source of truth

- Platform DB runtime/startup path: `alembic_platform.ini`
  - Used by `scripts/start_api_with_ssm.sh` for normal platform upgrades.
- Tenant DB path: `alembic_tenant.ini`
  - Requires `ALEMBIC_TENANT_DATABASE_URL` pointed at the tenant database.

## Why root alembic must remain for now

Do **not** delete root `alembic/` or `alembic.ini` until CI/scripts are migrated and DB revision truth is proven.

Main current dependencies:

1. `.github/workflows/alembic_guard.yml`
   - Requires `alembic/versions`, `alembic/env.py`, and `alembic.ini`.
   - Runs compile and guard checks scoped to `alembic/versions`.
2. `scripts/ci_check_alembic_down_revision.sh`
   - Scans `alembic/versions` (alongside platform/tenant trees) for `down_revision=None` hygiene.
3. `erp_audit.sh`
   - Audits for `alembic.ini`, `alembic/env.py`, `alembic/versions` and runs root Alembic checks.

## Retirement preconditions

Before retiring root `alembic/`:

1. Migrate CI guards/checks to the intended platform tree (`alembic_platform/versions`).
2. Update script audits/checkers that still require root files.
3. Prove DB revision truth (no environment depends on root-only revision chain for operational recovery).
4. Keep recovery docs explicit about which tree they target.

Until those are complete, root `alembic/` is legacy but still active.
