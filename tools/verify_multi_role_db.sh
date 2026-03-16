#!/bin/bash
# Verify multi-role onboarding DB outcomes.
# Run after manual_test_multi_role_onboarding.sh with actual app IDs, or
# pass APP_DRIVER_ID APP_DISP_ID as env vars.
#
# Confirms:
# 1. person_applications rows have application_type and requested_role_code
# 2. DRIVER approval → PersonRole(DRIVER) + DriverProfile
# 3. DISPATCHER approval → PersonRole(DISPATCHER), no DriverProfile

set -e
APP_DRIVER_ID="${APP_DRIVER_ID:?Set APP_DRIVER_ID}"
APP_DISP_ID="${APP_DISP_ID:?Set APP_DISP_ID}"

echo "=== DB verification: person_applications (invite rows) ==="
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
  SELECT id, application_type, requested_role_code, status, first_name, last_name
  FROM person_applications
  WHERE id IN ($APP_DRIVER_ID, $APP_DISP_ID);"

echo ""
echo "=== DB verification: PersonRole + DriverProfile (approval outcomes) ==="
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
  SELECT pr.person_id, pr.role_code, dp.id AS driver_profile_id
  FROM person_roles pr
  LEFT JOIN driver_profiles dp ON dp.person_id = pr.person_id AND dp.tenant_id = pr.tenant_id
  WHERE pr.person_id IN (
    SELECT person_id FROM person_applications WHERE id IN ($APP_DRIVER_ID, $APP_DISP_ID)
  )
  ORDER BY pr.role_code;"

echo ""
echo "Expected: DRIVER row has non-null driver_profile_id; DISPATCHER row has null driver_profile_id."
