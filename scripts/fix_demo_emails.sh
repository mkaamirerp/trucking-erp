#!/usr/bin/env bash
# Update @demo.local → @demo.test in the demo tenant's drivers table so email validation passes.
# Run from repo root. Uses DATABASE_URL or POSTGRES_ADMIN_URL for platform DB; resolves demo tenant's db_name.
set -e
cd "$(git rev-parse --show-toplevel 2>/dev/null || true)"
: "${POSTGRES_ADMIN_URL:=$DATABASE_URL}"
if [ -z "$POSTGRES_ADMIN_URL" ]; then
  echo "Set DATABASE_URL or POSTGRES_ADMIN_URL" >&2
  exit 1
fi
# psql needs postgresql:// not postgresql+asyncpg://
PSQL_URL="${POSTGRES_ADMIN_URL/postgresql+asyncpg/postgresql}"
# Get demo tenant db_name from platform DB (default DB from URL)
PLATFORM_DB="${PSQL_URL##*/}"
PLATFORM_DB="${PLATFORM_DB%%\?*}"
TENANT_DB=$(psql "$PSQL_URL" -t -A -c "SELECT db_name FROM platform_tenants WHERE slug = 'demo' LIMIT 1;" 2>/dev/null || true)
TENANT_DB=$(echo "$TENANT_DB" | tr -d '\r\n ')
if [ -z "$TENANT_DB" ]; then
  echo "No tenant with slug 'demo' found in platform_tenants (or db_name is null)." >&2
  exit 1
fi
echo "Updating drivers in tenant DB: $TENANT_DB"
TENANT_URL="${PSQL_URL/%\/${PLATFORM_DB}/\/${TENANT_DB}}"
psql "$TENANT_URL" -c "UPDATE drivers SET email = REPLACE(email, '@demo.local', '@demo.test') WHERE email LIKE '%@demo.local';"
echo "Done. Refresh the dashboard to see drivers."
