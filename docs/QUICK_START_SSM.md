# Quick Start: SSM Password Setup

This is a quick reference for the one-time SSM password setup. For full documentation, see `docs/secrets.md`.

## Immediate Next Steps

### Step 1: Verify SSM Has the Password

Run this command on your EC2 host:

```bash
aws ssm get-parameters-by-path \
  --path "/truckerp/prod/platform/" \
  --with-decryption \
  --recursive \
  --query "Parameters[?Name=='/truckerp/prod/platform/POSTGRES_PASSWORD'].{Name:Name,Type:Type,Len:Length(Value)}" \
  --output table
```

**Expected result:**
- A table row showing `Len` with a value > 0

**If you get no rows or Len = 0:**

Create the parameter:

```bash
aws ssm put-parameter \
  --name "/truckerp/prod/platform/POSTGRES_PASSWORD" \
  --value "YOUR_ACTUAL_POSTGRES_PASSWORD" \
  --type SecureString \
  --overwrite
```

Replace `YOUR_ACTUAL_POSTGRES_PASSWORD` with your real password.

### Step 2: Restart the API Container

```bash
cd /home/admin/trucking_erp
docker compose -f docker-compose.yml restart truckerp-api
```

The modified `start_api_with_ssm.sh` will now:
1. Fetch all secrets from SSM
2. Validate that `POSTGRES_PASSWORD` is present and non-empty
3. Exit with a clear error if validation fails
4. Start the API only if all required secrets are valid

### Step 3: Test DB Access

```bash
# Test connection
./scripts/db_run.sh 'PGPASSWORD="${POSTGRES_PASSWORD}" psql -h truckerp-postgres -U postgres -d postgres -c "select 1;"'
```

**Expected result:** `?column? | 1`

**If you get "password authentication failed":**

The Postgres volume was initialized with a different password. Sync it:

```bash
./scripts/db_run.sh 'PGPASSWORD="${POSTGRES_PASSWORD}" psql -h truckerp-postgres -U postgres -d postgres -c "ALTER USER postgres WITH PASSWORD '\''${POSTGRES_PASSWORD}'\'';"'
```

Then retest.

### Step 4: Run Migrations

From now on, **always** use `scripts/db_run.sh` for migrations:

```bash
# Platform DB (control plane) — alembic_platform.ini (same config the API runs at startup)
./scripts/db_run.sh 'alembic -c alembic_platform.ini upgrade head'

# Tenant DB (per-tenant database) — locked wrapper scripts/tenant_upgrade_head.sh; example ALEMBIC_TENANT_DATABASE_URL for tenant_demo
./scripts/db_run.sh bash -c 'export ALEMBIC_TENANT_DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@truckerp-postgres:5432/tenant_demo" && bash scripts/tenant_upgrade_head.sh'

# Fleet-wide tenant upgrades — app/scripts/tenant_fleet_upgrade_head.py
./scripts/db_run.sh python -m app.scripts.tenant_fleet_upgrade_head
```

**Legacy:** Root `alembic.ini` / `alembic/versions/` is not the routine platform path. Use it only if a recovery document explicitly tells you to. Normal platform work: `alembic_platform.ini`.

**Tenant Alembic (non-operator):** Do not use raw `alembic -c alembic_tenant.ini upgrade head` for routine upgrades—it bypasses preflight. Reserve direct tenant Alembic for local experiments or autogenerate/revision work unless a doc says otherwise.

## What Changed

1. **`scripts/start_api_with_ssm.sh`**
   - Added fail-closed validation for `DATABASE_URL`, `POSTGRES_ADMIN_URL`, `POSTGRES_PASSWORD`
   - API will not start if any required secret is missing or empty

2. **`scripts/db_run.sh`** (new file)
   - Universal wrapper for all DB commands
   - Automatically loads `/run/secrets/truckerp.env` before running commands
   - No more typing passwords manually

3. **`docs/secrets.md`** (new file)
   - Complete documentation of the SSM-only password policy
   - Troubleshooting guide
   - Examples for all common operations

## Testing Checklist

- [ ] SSM parameter exists and has Len > 0
- [ ] API container restarts successfully (no FATAL errors)
- [ ] `./scripts/db_run.sh 'PGPASSWORD="${POSTGRES_PASSWORD}" psql ...'` returns `?column? | 1`
- [ ] Platform migrations work: `./scripts/db_run.sh 'alembic -c alembic_platform.ini upgrade head'`
- [ ] Tenant migrations work: `./scripts/db_run.sh bash -c 'export ALEMBIC_TENANT_DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@truckerp-postgres:5432/tenant_demo" && bash scripts/tenant_upgrade_head.sh'`

## The Rule (Remember Forever)

**Never type, hardcode, or pass DB passwords manually.**

Always use:
- SSM for storage
- `start_api_with_ssm.sh` for fetching/validating at runtime
- `db_run.sh` for any command that needs DB access

If you see yourself about to type a password: **STOP** and use `db_run.sh` instead.
