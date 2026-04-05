#!/usr/bin/env bash
# =============================================================================
# CLEAN SLATE: Drop every tenant database and reset the platform DB.
# Use when you want to start completely fresh (all tenants gone, platform empty).
#
# What it does:
#   1. Drops every database whose name starts with "tenant_" (terminates
#      connections first).
#   2. Resets the platform database: DROP SCHEMA public CASCADE; CREATE SCHEMA public.
#   3. Runs platform migrations (alembic_platform.ini upgrade head).
#
# Requirements:
#   - Docker: truckerp-postgres and truckerp-api running.
#   - Platform DB name must match your DATABASE_URL (default: trucking_erp).
#   - For step 3, truckerp-api must have /run/secrets/truckerp.env (run
#     ./scripts/start_api_with_ssm.sh first, or ensure env is loaded).
#
# Usage:
#   ./scripts/clean_slate_postgres.sh
#   PLATFORM_DB=my_platform ./scripts/clean_slate_postgres.sh  # override platform DB name
#
# WARNING: This is destructive. All tenant data and all platform data are lost.
# =============================================================================
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-truckerp-postgres}"
API_CONTAINER="${API_CONTAINER:-truckerp-api}"
# Platform DB name (must match the DB in DATABASE_URL; default from docker-compose POSTGRES_DB)
PLATFORM_DB="${PLATFORM_DB:-trucking_erp}"
ENV_FILE="${ENV_FILE:-/run/secrets/truckerp.env}"

echo "=============================================="
echo "CLEAN SLATE: Drop all tenant DBs + reset platform"
echo "=============================================="
echo "  PG container:    $PG_CONTAINER"
echo "  API container:   $API_CONTAINER"
echo "  Platform DB:     $PLATFORM_DB"
echo "=============================================="
echo ""
read -r -p "This will DROP all tenant_* databases and reset platform DB. Type 'yes' to continue: " confirm
if [[ "$confirm" != "yes" ]]; then
  echo "Aborted."
  exit 1
fi

# ----- 1. Drop all tenant_* databases -----
echo ""
echo "Step 1: Dropping all tenant_* databases..."

# List tenant DBs (exclude system DBs)
TENANT_DBS=$(docker exec "$PG_CONTAINER" psql -U postgres -d postgres -tAc "
  SELECT datname FROM pg_database
  WHERE datname LIKE 'tenant_%'
  AND datname NOT IN ('postgres', 'template0', 'template1');
" 2>/dev/null || true)

if [[ -z "$TENANT_DBS" ]]; then
  echo "  No tenant_* databases found."
else
  for db in $TENANT_DBS; do
    db=$(echo "$db" | tr -d '[:space:]')
    [[ -z "$db" ]] && continue
    echo "  Terminating connections and dropping: $db"
    docker exec "$PG_CONTAINER" psql -U postgres -d postgres -c "
      SELECT pg_terminate_backend(pid) FROM pg_stat_activity
      WHERE datname = '$db' AND pid <> pg_backend_pid();
    " 2>/dev/null || true
    docker exec "$PG_CONTAINER" psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS \"$db\";"
    echo "  Dropped: $db"
  done
fi

# ----- 2. Reset platform DB (drop schema public, recreate) -----
echo ""
echo "Step 2: Resetting platform DB ($PLATFORM_DB)..."

# Ensure platform DB exists (create if missing, e.g. after full wipe)
docker exec "$PG_CONTAINER" psql -U postgres -d postgres -tAc "
  SELECT 1 FROM pg_database WHERE datname = '$PLATFORM_DB';
" | grep -q 1 || docker exec "$PG_CONTAINER" psql -U postgres -d postgres -c "CREATE DATABASE \"$PLATFORM_DB\";"

docker exec "$PG_CONTAINER" psql -U postgres -d postgres -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE datname = '$PLATFORM_DB' AND pid <> pg_backend_pid();
" 2>/dev/null || true

docker exec "$PG_CONTAINER" psql -U postgres -d "$PLATFORM_DB" -c "
  DROP SCHEMA IF EXISTS public CASCADE;
  CREATE SCHEMA public;
  GRANT ALL ON SCHEMA public TO postgres;
  GRANT ALL ON SCHEMA public TO public;
"

echo "  Platform schema reset (empty)."

# ----- 3. Run platform migrations -----
echo ""
echo "Step 3: Running platform migrations (alembic_platform.ini upgrade head)..."

if ! docker exec "$API_CONTAINER" test -f "$ENV_FILE" 2>/dev/null; then
  echo "  WARNING: $ENV_FILE not found in $API_CONTAINER."
  echo "  Run ./scripts/start_api_with_ssm.sh first, or set DATABASE_URL in the container."
  echo "  You can run migrations manually:"
  echo "    ./scripts/db_run.sh 'cd /app && alembic -c alembic_platform.ini upgrade head'"
  exit 0
fi

docker exec "$API_CONTAINER" sh -lc "
  set -a
  . $ENV_FILE
  set +a
  cd /app && alembic -c alembic_platform.ini upgrade head
"

echo ""
echo "=============================================="
echo "Clean slate complete."
echo "  - All tenant_* databases dropped."
echo "  - Platform DB ($PLATFORM_DB) reset and migrated to head."
echo "=============================================="
