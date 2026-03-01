# SSM_ENV Dev/Prod Namespace Split — Implementation & Runbook

## 1. Patch summary

### scripts/start_api_with_ssm.sh

- **Add** after `REGION=...`: `SSM_ENV="${SSM_ENV:-prod}"` and comment that dev uses `/truckerp/dev/...`, default prod uses `/truckerp/prod/...`.
- **Change** fetch paths from hardcoded `/truckerp/prod/platform/` and `/truckerp/prod/shared/` to `/truckerp/${SSM_ENV}/platform/` and `/truckerp/${SSM_ENV}/shared/`.
- **Change** log line to: `Secrets loaded from SSM (SSM_ENV=${SSM_ENV}) to $SECRETS_FILE`.

No other changes: tmpfs, truckerp.env, ALEMBIC_TENANT_DATABASE_URL injection, and not stripping TENANT_DATABASE_URL are unchanged.

### docker-compose.dev.yml

- **Add** under `truckerp-api` `environment`: `SSM_ENV: dev` (before existing TOOLS_DEV_*).

---

## 2. One-time AWS CLI: create dev SSM params

Run from a shell where AWS CLI is configured. Uses prod values to create dev params; **TENANT_DATABASE_URL** is set to use DB **tenant_demo** (same host/user/password as prod). **Redact passwords** in any pasted output.

```bash
set -e
REGION="${AWS_REGION:-us-east-1}"

# 1) Get prod values (redact when pasting)
PROD_DATABASE_URL=$(aws ssm get-parameter --name "/truckerp/prod/platform/DATABASE_URL" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)
PROD_POSTGRES_ADMIN_URL=$(aws ssm get-parameter --name "/truckerp/prod/platform/POSTGRES_ADMIN_URL" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)
PROD_POSTGRES_PASSWORD=$(aws ssm get-parameter --name "/truckerp/prod/platform/POSTGRES_PASSWORD" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)
PROD_TENANT_URL=$(aws ssm get-parameter --name "/truckerp/prod/platform/TENANT_DATABASE_URL" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)
PROD_JWT=$(aws ssm get-parameter --name "/truckerp/prod/shared/JWT_SECRET" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)

# 2) Dev TENANT_DATABASE_URL: same URL as prod but DB name = tenant_demo (replace last path segment)
#    Assumes format postgresql+asyncpg://user:pass@host:port/DBNAME
DEV_TENANT_URL=$(echo "$PROD_TENANT_URL" | sed -E 's|/([^/]+)$|/tenant_demo|')

# 3) Create /truckerp/dev/platform/ and /truckerp/dev/shared/ parameters (SecureString, overwrite)
aws ssm put-parameter --name "/truckerp/dev/platform/DATABASE_URL" \
  --value "$PROD_DATABASE_URL" --type SecureString --overwrite --region "$REGION"
aws ssm put-parameter --name "/truckerp/dev/platform/POSTGRES_ADMIN_URL" \
  --value "$PROD_POSTGRES_ADMIN_URL" --type SecureString --overwrite --region "$REGION"
aws ssm put-parameter --name "/truckerp/dev/platform/POSTGRES_PASSWORD" \
  --value "$PROD_POSTGRES_PASSWORD" --type SecureString --overwrite --region "$REGION"
aws ssm put-parameter --name "/truckerp/dev/platform/TENANT_DATABASE_URL" \
  --value "$DEV_TENANT_URL" --type SecureString --overwrite --region "$REGION"
aws ssm put-parameter --name "/truckerp/dev/shared/JWT_SECRET" \
  --value "$PROD_JWT" --type SecureString --overwrite --region "$REGION"

echo "Dev SSM parameters created. Redact passwords if you paste this output."
```

**JWT_SECRET:** Prod value is copied so dev can use the same JWT for local testing. Use a different secret for dev if you want strict dev/prod token separation (then generate and put a new value for `/truckerp/dev/shared/JWT_SECRET`).

**Note:** The script requires `POSTGRES_PASSWORD` in SSM; the block above copies it from prod to dev. If your prod path differs, add or adjust the corresponding `get-parameter` and `put-parameter` for `POSTGRES_PASSWORD`.

### Invite link and OTP emails (SMTP)

For driver onboarding **invite link** emails and signup **OTP** emails to be sent, the API must have SMTP configured. Same source as other secrets (e.g. SSM or `truckerp.env`):

- `SMTP_HOST`
- `SMTP_FROM_ADDRESS`
- `SMTP_PORT` (default 587)
- `SMTP_USERNAME` / `SMTP_PASSWORD` (if your server requires auth)
- Optional: `SMTP_USE_TLS` (default true), `SMTP_USE_SSL` (default false)

If these are missing, invite-link generation still returns a link but `email_sent` is false and the UI shows that email could not be sent. Add these parameters to your SSM path (e.g. `/truckerp/prod/shared/` or `/truckerp/dev/shared/`) so the startup script writes them into the env the API uses.

---

## 3. Acceptance checks

Run after rebuilding/restarting API with dev compose and after creating dev SSM params.

### 3.1 Env file (inside container)

```bash
docker exec truckerp-api sh -lc 'grep -E "^(SSM_ENV|TENANT_DATABASE_URL|ALEMBIC_TENANT_DATABASE_URL|DATABASE_URL)=" /run/secrets/truckerp.env'
```

**Expected:**  
- `SSM_ENV=dev` may appear only if you export it into the file; otherwise it is set in the process env from compose. So either `SSM_ENV=dev` is present, or at least:  
- `TENANT_DATABASE_URL=.../tenant_demo`  
- `ALEMBIC_TENANT_DATABASE_URL=.../tenant_demo`  
- `DATABASE_URL=.../trucking_erp`

### 3.2 DB list (tenant_demo exists)

```bash
docker exec truckerp-postgres psql -U postgres -d postgres -c '\l'
```

**Expected:** `tenant_demo` in the list; no DB named `truckerp` required.

### 3.3 Tenant migration

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini upgrade head'
```

**Expected:** No error like `database "truckerp" does not exist`; migration runs to head (or reports already at head).

---

## 4. Rebuild/restart after code changes

```bash
cd /home/admin/trucking_erp
docker compose -f docker-compose.yml -f docker-compose.dev.yml build truckerp-api
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d truckerp-api
```

Then run the acceptance checks above.
