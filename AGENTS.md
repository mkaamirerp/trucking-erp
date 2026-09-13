# AGENTS.md

## Cursor Cloud specific instructions

### Architecture Overview

TruckERP is a multi-tenant SaaS ERP for trucking companies. It has two main services:

| Service | Path | Port | Command |
|---------|------|------|---------|
| **FastAPI Backend** | `app/` | 8000 | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` |
| **Vite Frontend** | `apps/web/` | 5173 | `cd apps/web && npm run dev` |

PostgreSQL is required (platform DB `trucking_erp` + per-tenant DBs `tenant_<slug>`).

### Running Services

- **Backend**: Activate the venv (`source .venv/bin/activate`) then run uvicorn from the repo root.
- **Frontend**: `cd apps/web && npm run dev`. The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.
- **PostgreSQL**: Must be running and accessible at the hostname in `DATABASE_URL`. Start with `sudo pg_ctlcluster 16 main start`.

### Database Setup (fresh environment)

The `.env` file must exist in the repo root with at least `DATABASE_URL`. The `app/core/config.py` **rejects localhost/127.0.0.1/::1** as the DB hostname (Docker-era guard). Use the machine hostname (e.g., `cursor`) or a non-loopback address instead.

Migrations require running **both** the legacy chain and the platform chain in order:

1. `alembic -c alembic.ini upgrade head` (creates tables including `platform_company_profiles`, `platform_otp_tokens`, etc.)
2. Update `alembic_version` to bridge to the platform chain: `psql -c "UPDATE alembic_version SET version_num = '0009_provision_hardening';"` and if needed `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(100);`
3. `alembic -c alembic_platform.ini upgrade head` (applies platform-specific migrations 0010+)
4. Manually add `session_version` column: `ALTER TABLE platform_users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1;`
5. Manually add columns from migration 0010 if missing: `base_currency`, `timezone`, `country_code`, `billing_status`, `billing_provider` on `platform_tenants`.

### Testing

- **Backend tests**: `python -m pytest tests/ -v` (requires `DATABASE_URL` env var set)
- **CI tests** (no DB required): `python -m pytest tests/ci/ -v`
- **Frontend lint**: `cd apps/web && npm run lint` (currently echoes "lint not configured")
- **Python lint**: `ruff check app/`
- **TypeScript check**: `cd apps/web && npx tsc --noEmit` (has pre-existing missing-module errors)

### Known Pre-existing Issues

- `app/services/tenant_provisioning.py` line 128 references `_ensure_asyncpg_url` which is undefined; should be `to_async_pg_url`. This breaks the signup OTP verification + tenant provisioning flow.
- Frontend has missing module imports (`./contexts/AuthContext`, `./components/ErrorBoundary`, `./tenant`, `./routes`, etc.) causing Vite and TypeScript errors.
- 5 of 9 pytest tests fail with pre-existing assertion mismatches unrelated to environment setup.

### Dev Environment .env Template

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@cursor:5432/trucking_erp
POSTGRES_ADMIN_URL=postgresql+asyncpg://postgres:postgres@cursor:5432/trucking_erp
TENANT_DB_APP_USER=postgres
TENANT_DB_APP_PASSWORD=postgres
JWT_SECRET=dev-local-secret-key-12345
BASE_DOMAIN=localhost
COOKIE_DOMAIN=localhost
ENVIRONMENT=dev
```
