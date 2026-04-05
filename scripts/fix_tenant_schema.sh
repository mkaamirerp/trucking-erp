#!/usr/bin/env bash
# =============================================================================
# Tenant Schema Fix Script
# Fixes common schema issues from migration conflicts
# =============================================================================
set -euo pipefail

TENANT_DB="${1:-tenant_demo}"

echo "🔧 Fixing schema for tenant database: $TENANT_DB"
echo ""

# Check if db_run.sh exists
if [[ ! -f "./scripts/db_run.sh" ]]; then
  echo "❌ ERROR: scripts/db_run.sh not found."
  echo "   This script requires db_run.sh to run commands with proper credentials."
  exit 1
fi

echo "Step 1: Checking person_roles table..."

# Check if is_primary column exists
HAS_IS_PRIMARY=$(./scripts/db_run.sh "PGPASSWORD=\"\${POSTGRES_PASSWORD}\" psql -h truckerp-postgres -U postgres -d $TENANT_DB -tAc \"SELECT COUNT(*) FROM information_schema.columns WHERE table_name='person_roles' AND column_name='is_primary';\"" 2>/dev/null || echo "0")

if [[ "$HAS_IS_PRIMARY" == "0" ]]; then
  echo "  ⚠️  Missing is_primary column. Adding it..."
  ./scripts/db_run.sh "PGPASSWORD=\"\${POSTGRES_PASSWORD}\" psql -h truckerp-postgres -U postgres -d $TENANT_DB -c \"ALTER TABLE person_roles ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;\""
  echo "  ✅ is_primary column added."
else
  echo "  ✅ is_primary column exists."
fi

echo ""
echo "Step 2: Checking for legacy 'role' column..."

# Check if 'role' column exists (should be 'role_code')
HAS_ROLE=$(./scripts/db_run.sh "PGPASSWORD=\"\${POSTGRES_PASSWORD}\" psql -h truckerp-postgres -U postgres -d $TENANT_DB -tAc \"SELECT COUNT(*) FROM information_schema.columns WHERE table_name='person_roles' AND column_name='role';\"" 2>/dev/null || echo "0")

if [[ "$HAS_ROLE" != "0" ]]; then
  echo "  ⚠️  Found legacy 'role' column. Renaming to 'role_code'..."
  ./scripts/db_run.sh "PGPASSWORD=\"\${POSTGRES_PASSWORD}\" psql -h truckerp-postgres -U postgres -d $TENANT_DB -c \"ALTER TABLE person_roles RENAME COLUMN role TO role_code;\""
  echo "  ✅ Column renamed to role_code."
else
  echo "  ✅ No legacy 'role' column found."
fi

echo ""
echo "Step 3: Checking people.is_active column..."

HAS_PEOPLE_IS_ACTIVE=$(./scripts/db_run.sh "PGPASSWORD=\"\${POSTGRES_PASSWORD}\" psql -h truckerp-postgres -U postgres -d $TENANT_DB -tAc \"SELECT COUNT(*) FROM information_schema.columns WHERE table_name='people' AND column_name='is_active';\"" 2>/dev/null || echo "0")

if [[ "$HAS_PEOPLE_IS_ACTIVE" == "0" ]]; then
  echo "  ⚠️  Missing people.is_active column. Adding it..."
  ./scripts/db_run.sh "PGPASSWORD=\"\${POSTGRES_PASSWORD}\" psql -h truckerp-postgres -U postgres -d $TENANT_DB -c \"ALTER TABLE people ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;\""
  echo "  ✅ people.is_active column added."
else
  echo "  ✅ people.is_active column exists."
fi

echo ""
echo "Step 4: Validating schema..."

# Run Python validation
./scripts/db_run.sh "python -c \"
import os
from app.services.tenant_schema_validation import validate_tenant_schema

tenant_db_url = f'postgresql+asyncpg://postgres:{os.environ[\"POSTGRES_PASSWORD\"]}@truckerp-postgres:5432/$TENANT_DB'
errors = validate_tenant_schema(tenant_db_url)

if errors:
    print('❌ Schema validation failed:')
    for err in errors:
        print(f'  - {err}')
    exit(1)
else:
    print('✅ Schema validation passed!')
\""

echo ""
echo "🎉 Schema fix complete for $TENANT_DB!"
