# Secrets Management – SSM-Only Password Policy

## Overview

This project uses a **fail-closed, SSM-only** secret management system. The Postgres password and other sensitive configuration values are stored exclusively in AWS Systems Manager (SSM) Parameter Store as SecureString values.

## The Rule

**DB passwords and DB URLs come ONLY from SSM.**

- At runtime, secrets are written to `/run/secrets/truckerp.env` by `scripts/start_api_with_ssm.sh`
- The API container uses this env file exclusively
- If any required secret is missing or empty, the API **must not start** and **must fail with a clear FATAL message**
- No secrets are ever hardcoded in:
  - `docker-compose.yml` or `docker-compose.*.yml`
  - `.env` files (except `.env.example` for documentation)
  - Inline commands or scripts
  - Code or configuration files

## SSM Parameter Paths

All secrets are stored under these SSM paths:

- `/truckerp/prod/platform/` – Platform-level secrets (DATABASE_URL, POSTGRES_ADMIN_URL, POSTGRES_PASSWORD, JWT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, etc.)
- `/truckerp/prod/shared/` – Shared secrets (SMTP, external API keys, etc.)

### Required Parameters

The following parameters **must** exist and be non-empty:

- `DATABASE_URL` – Async connection string for the platform database
- `POSTGRES_ADMIN_URL` – Sync psycopg2 connection string for admin operations
- `POSTGRES_PASSWORD` – Raw Postgres password (used by scripts and migrations)

## How Secrets Flow

```
AWS SSM Parameter Store
         ↓
scripts/start_api_with_ssm.sh (fetches with --with-decryption)
         ↓
/run/secrets/truckerp.env (tmpfs inside container)
         ↓
API process (uvicorn with --env-file)
         ↓
Application code (os.getenv)
```

## Running DB Commands (Alembic, psql, etc.)

**NEVER** type or pass passwords manually. Always use the `scripts/db_run.sh` wrapper:

```bash
# Tenant migrations
./scripts/db_run.sh 'ALEMBIC_TENANT_DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@truckerp-postgres:5432/tenant_demo" alembic -c alembic_tenant.ini upgrade head'

# Platform migrations
./scripts/db_run.sh 'alembic -c alembic.ini upgrade head'

# Direct psql check
./scripts/db_run.sh 'PGPASSWORD="${POSTGRES_PASSWORD}" psql -h truckerp-postgres -U postgres -d postgres -c "select 1;"'
```

This wrapper:
1. Verifies the API container is running and `/run/secrets/truckerp.env` exists
2. Runs the command inside the container with the env file loaded
3. Uses `$POSTGRES_PASSWORD` (and other vars) from the env file—no hardcoded values

## Fail-Closed Design

The `scripts/start_api_with_ssm.sh` script validates that required secrets are present and non-empty **before starting the API**. If validation fails, the container exits immediately with:

```
FATAL: POSTGRES_PASSWORD is EMPTY in /run/secrets/truckerp.env. Refusing to start.
```

This ensures:
- No silent failures
- No "API looks up but migrations fail later"
- Immediate, obvious feedback when secrets are misconfigured

## Adding a New Secret

1. Add the parameter to SSM under `/truckerp/prod/platform/` or `/truckerp/prod/shared/`:
   ```bash
   aws ssm put-parameter \
     --name "/truckerp/prod/platform/NEW_SECRET" \
     --value "secret_value" \
     --type SecureString \
     --overwrite
   ```

2. If the secret is **required** (API cannot start without it):
   - Add it to the `required_vars` array in `scripts/start_api_with_ssm.sh`

3. Restart the API container (it will fetch and validate the new parameter)

### Gmail OAuth (optional)

For the tenant Gmail Connect flow, add these to `/truckerp/<env>/platform/` (use `prod` or `dev` per SSM_ENV):

```bash
aws ssm put-parameter \
  --name "/truckerp/prod/platform/GOOGLE_CLIENT_ID" \
  --value "YOUR_CLIENT_ID.apps.googleusercontent.com" \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name "/truckerp/prod/platform/GOOGLE_CLIENT_SECRET" \
  --value "YOUR_CLIENT_SECRET" \
  --type SecureString \
  --overwrite
```

Restart the API after adding. See `docs/GMAIL_OAUTH_SETUP.md` for Google Cloud Console setup.

## Troubleshooting

### "FATAL: POSTGRES_PASSWORD missing in /run/secrets/truckerp.env"

**Cause:** The SSM parameter `/truckerp/prod/platform/POSTGRES_PASSWORD` does not exist or is not under a fetched path.

**Fix:**
1. Check if the parameter exists:
   ```bash
   aws ssm get-parameter --name "/truckerp/prod/platform/POSTGRES_PASSWORD" --with-decryption --query "Parameter.Value" --output text
   ```
2. If missing, create it:
   ```bash
   aws ssm put-parameter \
     --name "/truckerp/prod/platform/POSTGRES_PASSWORD" \
     --value "your_postgres_password" \
     --type SecureString \
     --overwrite
   ```
3. Restart the API container

### "FATAL: POSTGRES_PASSWORD is EMPTY in /run/secrets/truckerp.env"

**Cause:** The parameter exists but has an empty value, or IAM/KMS permissions prevent decryption.

**Fix:**
1. Check the parameter value length:
   ```bash
   aws ssm get-parameters-by-path \
     --path "/truckerp/prod/platform/" \
     --with-decryption \
     --recursive \
     --query "Parameters[?Name=='/truckerp/prod/platform/POSTGRES_PASSWORD'].{Name:Name,Len:Length(Value)}" \
     --output table
   ```
2. If `Len = 0`, update the parameter with a valid value
3. If `Len > 0` but still empty in the env file, check IAM/KMS permissions for the EC2 instance or ECS task role

### "Password authentication failed for user postgres"

**Cause:** The password in SSM doesn't match the password the Postgres server was initialized with.

**Fix (dev/test only):**
1. Ensure `/run/secrets/truckerp.env` has the correct password from SSM
2. Reset Postgres to use that password:
   ```bash
   ./scripts/db_run.sh 'PGPASSWORD="${POSTGRES_PASSWORD}" psql -h truckerp-postgres -U postgres -d postgres -c "ALTER USER postgres WITH PASSWORD '\''${POSTGRES_PASSWORD}'\'';"'
   ```
3. Or, if you know the current DB password: update SSM to match it, then restart the API

## Cursor/AI Instructions

When asked to make code or infrastructure changes:

- **DO NOT** hardcode passwords anywhere
- **DO NOT** add passwords to `docker-compose.yml` environment sections
- **DO NOT** create `.env` files with secrets (only `.env.example` for documentation)
- **DO** use `scripts/db_run.sh` for all DB commands
- **DO** ensure any new required secrets are validated in `scripts/start_api_with_ssm.sh`
- **DO** add new secrets to SSM first, then reference them via `$VAR_NAME` from the env file

## References

- SSM path configuration: `scripts/start_api_with_ssm.sh` (lines defining `fetch_path` calls)
- Fail-closed validation: `scripts/start_api_with_ssm.sh` (search for "FAIL-CLOSED")
- DB command wrapper: `scripts/db_run.sh`
- Alembic env setup: `alembic_platform/env.py`, `alembic_tenant/env.py`
