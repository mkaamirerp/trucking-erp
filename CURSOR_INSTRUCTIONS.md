# Cursor instructions — TruckERP

This project uses **`.cursor/rules/`** for AI and human guidance. Those rules are always applied. This file is a short pointer and cheat sheet.

## Where the real rules live

- **`.cursor/rules/`** — Rebuild/restart, tenant vs platform Alembic, SSM guards, auth-signup policy, tenant migrations, post-code-change steps.
- **`docker compose`** — Always use v2 (space), with both files: `-f docker-compose.yml -f docker-compose.dev.yml`. Working directory: `/home/admin/trucking_erp`.

## Must-do after code changes

- **Backend (routers, models, middleware, config):** Rebuild + restart API, then confirm logs.
- **Frontend:** `cd apps/web && npm run build` then restart nginx.
- **Never** run tenant Alembic from the host; use the container wrapper (see `.cursor/rules/tenant-migrations.mdc`).

## Critical guards

- **Secrets:** DEV uses `.env` only (no SSM/AWS). PROD uses SSM only (no `.env`). With dev compose, API starts with uvicorn and `env_file: .env`; with prod compose, API starts via `start_api_with_ssm.sh`. Do not commit `.env`.
- **DB split:** Platform DB (`get_db`) vs tenant DB (`get_tenant_db`). No mixing. Platform migrations: `alembic_platform.ini`. Tenant: `alembic_tenant.ini` + `ALEMBIC_TENANT_DATABASE_URL`.
- **Auth/signup:** Before editing `auth.py`, `public_signup.py`, `otp.py`, or related middleware, read the required docs cited in `.cursor/rules/auth-signup-change-policy.mdc`.

## Quick commands

| Goal              | Command |
|-------------------|--------|
| Rebuild + restart API | `cd /home/admin/trucking_erp && docker compose -f docker-compose.yml -f docker-compose.dev.yml build truckerp-api && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d truckerp-api` |
| Frontend build    | `cd apps/web && npm run build` |
| Restart nginx     | `docker compose -f docker-compose.yml -f docker-compose.dev.yml restart truckerp-nginx` |
| Tenant migrate (in container) | `docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh'` |

For full command lists and “when to do what,” see **`.cursor/rules/rebuild-restart-commands.mdc`**.
