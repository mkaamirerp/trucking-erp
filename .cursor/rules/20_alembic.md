# Alembic Safety (CRITICAL)

## Dual-track (actual repo layout)

- **Platform:** `alembic_platform.ini` → `alembic_platform/versions/`
- **Tenant:** `alembic_tenant.ini` → `alembic_tenant/versions/` (requires `ALEMBIC_TENANT_DATABASE_URL`)
- Root `alembic.ini` → `alembic/` is **not** the platform schema track. Do **not** use it for platform changes.

## Safety
- Never create/edit migrations unless explicitly asked.
- Migrations must be idempotent.
- No stamping unless explicitly approved (last resort).
- If a revision is missing: stop and diagnose revision graph (heads/history), then fix chain.

See also: `.cursor/rules/alembic-platform-tenant-config.mdc`, `.cursor/rules/tenant-migrations.mdc`, `.cursor/rules/ssm-and-tenant-hard-guards.mdc`.
