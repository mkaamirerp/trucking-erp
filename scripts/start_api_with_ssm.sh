#!/usr/bin/env bash
# =============================================================================
# IMPORTANT: DB passwords come ONLY from SSM → /run/secrets/truckerp.env.
# Never hardcode passwords in docker-compose, .env files, or inline commands.
# Always use db_run.sh for any DB command (Alembic, psql, etc.).
# If required secrets are missing or empty, this script MUST exit with a FATAL error.
# This stack uses prod SSM paths only (/truckerp/prod/...). No local .env fallback.
# =============================================================================
set -uo pipefail

SECRETS_FILE="/run/secrets/truckerp.env"
REGION="${AWS_REGION:-us-east-1}"
SSM_ENV="${SSM_ENV:-prod}"
if [[ "${SSM_ENV}" != "prod" ]]; then
  echo "FATAL: SSM_ENV must be prod for this deployment (got: ${SSM_ENV})." >&2
  exit 1
fi

# Run platform DB migrations then start the API (so signup/OTP tables exist).
run_migrations_and_start() {
  local env_file="$1"
  set -a
  # shellcheck source=/dev/null
  . "$env_file"
  set +a
  echo "Running platform DB migrations..."
  if ! (cd /app && alembic -c alembic_platform.ini upgrade head); then
    echo "FATAL: Platform DB migration failed. Fix the DB and restart." >&2
    exit 1
  fi
  echo "Migrations complete. Starting API."
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file "$env_file"
}

fetch_path () {
  local path="$1"
  aws ssm get-parameters-by-path \
    --path "$path" \
    --recursive \
    --with-decryption \
    --region "$REGION" \
    --output json \
    | jq -r '.Parameters[] | "\(.Name | split("/") | last)=\(.Value)"'
}

# Fetch SSM → truckerp.env (single prod namespace)
if {
  fetch_path "/truckerp/${SSM_ENV}/platform/"
  fetch_path "/truckerp/${SSM_ENV}/shared/"
} 2>/dev/null | awk -F= 'NF>=2 { a[$1]=$0 } END { for (k in a) print a[k] }' | sort > "$SECRETS_FILE" 2>/dev/null; then
  
  # ---- FAIL-CLOSED: required secrets must be present and non-empty ----
  required_vars=(
    DATABASE_URL POSTGRES_ADMIN_URL POSTGRES_PASSWORD
    LOGIN_TRUST_COOKIE_SECRET ENVIRONMENT
  )
  missing=0
  for v in "${required_vars[@]}"; do
    if ! grep -q "^${v}=" "$SECRETS_FILE"; then
      echo "FATAL: ${v} missing in $SECRETS_FILE. Refusing to start."
      missing=1
    else
      # Extract value after first '='
      val="$(grep "^${v}=" "$SECRETS_FILE" | head -n1 | cut -d= -f2-)"
      if [ -z "$val" ]; then
        echo "FATAL: ${v} is EMPTY in $SECRETS_FILE. Refusing to start."
        missing=1
      fi
    fi
  done
  if [ "$missing" -ne 0 ]; then
    exit 1
  fi
  # ----------------------------------------------------------------

  # Ensure tenant migrations always work
  if grep -q "^TENANT_DATABASE_URL=" "$SECRETS_FILE"; then
    turl="$(grep "^TENANT_DATABASE_URL=" "$SECRETS_FILE" | head -n1 | cut -d= -f2-)"
    if ! grep -q "^ALEMBIC_TENANT_DATABASE_URL=" "$SECRETS_FILE"; then
      echo "ALEMBIC_TENANT_DATABASE_URL=$turl" >> "$SECRETS_FILE"
    fi
  fi

  if [[ -s "$SECRETS_FILE" ]]; then
    if grep -q "^SMTP_FROM=" "$SECRETS_FILE" && ! grep -q "^SMTP_FROM_ADDRESS=" "$SECRETS_FILE"; then
      smtp_from=$(grep "^SMTP_FROM=" "$SECRETS_FILE" | head -n1 | cut -d= -f2-)
      echo "SMTP_FROM_ADDRESS=$smtp_from" >> "$SECRETS_FILE"
    fi
    if grep -q "^SMTP_STARTTLS=" "$SECRETS_FILE" && ! grep -q "^SMTP_USE_TLS=" "$SECRETS_FILE"; then
      smtp_tls=$(grep "^SMTP_STARTTLS=" "$SECRETS_FILE" | head -n1 | cut -d= -f2-)
      echo "SMTP_USE_TLS=$smtp_tls" >> "$SECRETS_FILE"
    fi
    echo "Secrets loaded from SSM (SSM_ENV=${SSM_ENV}) to $SECRETS_FILE"
    run_migrations_and_start "$SECRETS_FILE"
  fi
fi

echo "ERROR: No secrets from AWS SSM (/truckerp/prod/platform/ and /truckerp/prod/shared/). See docs/QUICK_START_SSM.md and docs/config-and-infra-guardrails.md" >&2
exit 1
