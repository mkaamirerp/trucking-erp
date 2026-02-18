# Clean slate: drop all tenants and reset platform DB

When you want to start completely fresh (no tenant DBs, no platform data).

## What gets wiped

- Every database whose name starts with `tenant_` (e.g. tenant_attia, tenant_erp) is dropped.
- The platform database (default: trucking_erp) is reset: DROP SCHEMA public CASCADE then CREATE SCHEMA public. All platform tables and data are removed.
- Then platform migrations are run (alembic_platform.ini upgrade head) so the platform DB has the current schema and is empty.

## Prerequisites

- Docker: truckerp-postgres and truckerp-api running.
- Platform DB name must match your DATABASE_URL (default from compose: trucking_erp).
- For migrations to run, the API container must have env (e.g. /run/secrets/truckerp.env). Run ./scripts/start_api_with_ssm.sh first if you use SSM.

## Usage

```bash
./scripts/clean_slate_postgres.sh
```

You will be prompted to type `yes` before anything is dropped.

Override the platform DB name if yours is different:

```bash
PLATFORM_DB=my_platform ./scripts/clean_slate_postgres.sh
```

## After clean slate

- Tenant DBs: None. New signups or admin-created tenants will create new tenant_* databases when provisioned.
- Platform DB: Empty but migrated (all tables present, no rows). You can sign up again and provision new tenants.

Warning: This is destructive. All tenant data and all platform data are permanently removed.
