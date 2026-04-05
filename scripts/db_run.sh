#!/usr/bin/env bash
# =============================================================================
# IMPORTANT: DB passwords come ONLY from SSM → /run/secrets/truckerp.env.
# Never hardcode passwords in docker-compose, .env files, or inline commands.
# Always use db_run.sh for any DB command (Alembic, psql, etc.).
# If required secrets are missing or empty, this script MUST exit with a FATAL error.
# =============================================================================
set -euo pipefail

# Run any command inside truckerp-api with SSM env sourced, from /app, args preserved.
# Works in non-TTY sessions (e.g. CI); uses -t only when stdin is a TTY.

ENV_FILE="/run/secrets/truckerp.env"
CONTAINER="truckerp-api"

if [ $# -eq 0 ]; then
  echo "Usage: $0 <command> [args...]"
  echo "Example (platform): $0 alembic -c alembic_platform.ini current"
  echo "Example (tenant operator): $0 bash -c 'export ALEMBIC_TENANT_DATABASE_URL=\"postgresql+asyncpg://postgres:\${POSTGRES_PASSWORD}@truckerp-postgres:5432/tenant_demo\" && bash scripts/tenant_upgrade_head.sh'"
  exit 1
fi

# -t only when stdin is a TTY (so non-interactive/CI runs work)
if [ -t 0 ]; then
  TTY_FLAG="-t"
else
  TTY_FLAG=""
fi

# Verify container exists and env file is present inside it
if ! docker exec "$CONTAINER" test -f "$ENV_FILE" 2>/dev/null; then
  echo "ERROR: $ENV_FILE not found inside $CONTAINER."
  echo "Run ./scripts/start_api_with_ssm.sh first to generate the env file."
  exit 1
fi

# _ is zeroth arg to sh -c; "$@" are the actual command args (preserved)
docker exec -i ${TTY_FLAG} "$CONTAINER" sh -lc '
  set -e
  set -a
  if [ ! -f /run/secrets/truckerp.env ]; then
    echo "ERROR: /run/secrets/truckerp.env not found inside container." >&2
    exit 1
  fi
  . /run/secrets/truckerp.env
  set +a
  cd /app
  exec "$@"
' _ "$@"
