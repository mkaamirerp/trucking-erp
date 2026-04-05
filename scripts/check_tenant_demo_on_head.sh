#!/usr/bin/env bash
# Dev/demo guardrail: tenant_demo DB must be at the current tenant migration head.
# Run on your demo box; fails if alembic_version in tenant_demo does not match
# the single head from: python -m alembic -c alembic_tenant.ini heads
set -e

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-truckerp-postgres}"
TENANT_DB="${TENANT_DB:-tenant_demo}"
PYTHON="${PYTHON:-python3}"

echo "Checking tenant_demo is on tenant migration head..."

# Get current tenant chain head (e.g. "fefd8f1df8d9 (head)")
HEADS_OUT=$("$PYTHON" -m alembic -c alembic_tenant.ini heads 2>&1)
HEAD_LINE=$(echo "$HEADS_OUT" | grep -E "^\w+.*\(head\)" | head -n1)
if [[ -z "$HEAD_LINE" ]]; then
  echo "Could not determine tenant head from: $HEADS_OUT"
  exit 1
fi
EXPECTED_HEAD=$(echo "$HEAD_LINE" | awk '{print $1}')
echo "Tenant chain head: $EXPECTED_HEAD"

# Get version_num from tenant_demo (requires docker + running postgres)
DB_VERSION=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d "$TENANT_DB" -t -A -c "SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d '\r\n' || true)
if [[ -z "$DB_VERSION" ]]; then
  echo "Skipping: could not read alembic_version from $TENANT_DB (container=$POSTGRES_CONTAINER). Run when demo DB is provisioned."
  exit 0
fi

echo "tenant_demo version_num: $DB_VERSION"

if [[ "$DB_VERSION" != "$EXPECTED_HEAD" ]]; then
  echo "ERROR: tenant_demo is not on tenant head. DB has $DB_VERSION, expected $EXPECTED_HEAD"
  echo "Fix (repo root, preflight wrapper): cd /home/admin/trucking_erp && ./scripts/db_run.sh bash -c 'export ALEMBIC_TENANT_DATABASE_URL=\"postgresql+asyncpg://postgres:\${POSTGRES_PASSWORD}@truckerp-postgres:5432/${TENANT_DB}\" && bash scripts/tenant_upgrade_head.sh'"
  exit 1
fi

echo "tenant_demo is on head ($EXPECTED_HEAD)."
