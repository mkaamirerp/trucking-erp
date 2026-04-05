# Alembic Safety (CRITICAL)

## Dual-track
- Platform migrations: alembic/
- Tenant migrations: alembic_tenant/

## Safety
- Never create/edit migrations unless explicitly asked.
- Migrations must be idempotent.
- No stamping unless explicitly approved (last resort).
- If a revision is missing: stop and diagnose revision graph (heads/history), then fix chain.
