#!/bin/sh
# Remove one disposable workspace after its tenant database has been dropped.
# Usage: ./tools/reset_signup.sh <slug> <email> <db_name>
#
# The database name must match platform_tenants.db_name for that slug.
# demo, ikl, tenant_demo, and tenant_ikl are always refused.
# An ACTIVE tenant is refused unless RESET_SIGNUP_ALLOW_ACTIVE equals that slug.
# The registry row is deleted only after DROP DATABASE is verified.
# Do not point this at a tenant whose drop cannot be confirmed.

set -eu

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <slug> <email> <db_name>" >&2
  echo "ACTIVE tenants require RESET_SIGNUP_ALLOW_ACTIVE=<slug>." >&2
  echo "demo, ikl, tenant_demo, and tenant_ikl are protected." >&2
  exit 1
fi

slug="$1"
email="$2"
db_name="$3"
allow_active="${RESET_SIGNUP_ALLOW_ACTIVE:-}"

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
. "$ROOT/tools/reset_signup_guard.sh"

reset_signup_validate_slug "$slug"
reset_signup_validate_email "$email"
reset_signup_validate_db_name "$db_name"
reset_signup_assert_not_protected "$slug" "$db_name"

COMPOSE="${RESET_SIGNUP_COMPOSE:-docker compose -f docker-compose.yml}"

lookup=$($COMPOSE exec -T truckerp-postgres psql -U postgres -d trucking_erp -At -F '|' -c \
  "SELECT id, status, COALESCE(db_name, '') FROM platform_tenants WHERE slug = '${slug}' LIMIT 1;")
if [ -z "$lookup" ]; then
  echo "No platform_tenants row for slug '${slug}'. Nothing was dropped or deleted." >&2
  exit 1
fi

registry_id=$(printf '%s' "$lookup" | cut -d '|' -f 1)
registry_status=$(printf '%s' "$lookup" | cut -d '|' -f 2)
registry_db=$(printf '%s' "$lookup" | cut -d '|' -f 3)

if [ "$registry_db" != "$db_name" ]; then
  echo "Refusing slug '${slug}': registry database '${registry_db}' does not match '${db_name}'. Registry row kept." >&2
  exit 1
fi

reset_signup_assert_not_protected "$slug" "$registry_db"
reset_signup_assert_active_allowed "$slug" "$registry_status" "$allow_active"

psql_postgres() {
  $COMPOSE exec -T truckerp-postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"
}

exists=$(psql_postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '${db_name}'") || {
  echo "Could not check whether '${db_name}' exists. Registry row ${registry_id} was not removed." >&2
  exit 1
}
dropped=0
allow_changed=0
original_allow=""

# Restore the prior ALLOW_CONNECTIONS value only when this script changed it
# and the database is still present. A dropped database is never recreated.
restore_allow_connections() {
  if [ "$allow_changed" != "1" ]; then
    return 0
  fi
  present=$(psql_postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '${db_name}'") || {
    echo "Recovery failure: could not tell whether '${db_name}' still exists. ALLOW_CONNECTIONS was not restored. Registry row ${registry_id} was not removed." >&2
    return 1
  }
  if [ "$present" != "1" ]; then
    echo "Database '${db_name}' is already absent. It was not recreated. Registry row ${registry_id} was not removed." >&2
    allow_changed=0
    return 0
  fi
  if ! psql_postgres -c "ALTER DATABASE \"${db_name}\" ALLOW_CONNECTIONS ${original_allow};"; then
    echo "Recovery failure: could not restore ALLOW_CONNECTIONS ${original_allow} on '${db_name}'. The database may still reject connections. Registry row ${registry_id} was not removed." >&2
    return 1
  fi
  echo "Restored ALLOW_CONNECTIONS ${original_allow} on '${db_name}'. Registry row ${registry_id} was not removed." >&2
  allow_changed=0
  return 0
}

fail_before_drop() {
  if ! restore_allow_connections; then
    exit 1
  fi
  echo "$1" >&2
  exit 1
}

if [ "$exists" = "1" ]; then
  original_allow=$(psql_postgres -Atc "SELECT CASE WHEN datallowconn THEN 'true' ELSE 'false' END FROM pg_database WHERE datname = '${db_name}'") || {
    echo "Could not read ALLOW_CONNECTIONS for '${db_name}'. Connections were not changed. Registry row ${registry_id} was not removed." >&2
    exit 1
  }
  case "$original_allow" in
    true|false) ;;
    *)
      echo "Refusing unexpected ALLOW_CONNECTIONS value for '${db_name}'. Connections were not changed. Registry row ${registry_id} was not removed." >&2
      exit 1
      ;;
  esac

  # Reject new API pool checkouts before terminate, then force-drop leftovers.
  if ! psql_postgres -c "ALTER DATABASE \"${db_name}\" ALLOW_CONNECTIONS false;"; then
    echo "Could not set ALLOW_CONNECTIONS false on '${db_name}'. Connections were left unchanged. Registry row ${registry_id} was not removed." >&2
    exit 1
  fi
  allow_changed=1

  if ! psql_postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${db_name}' AND pid <> pg_backend_pid();"; then
    fail_before_drop "Could not terminate sessions on '${db_name}'. Database was not dropped. Registry row ${registry_id} was not removed."
  fi
  if ! psql_postgres -c "DROP DATABASE \"${db_name}\" WITH (FORCE);"; then
    fail_before_drop "Database drop failed for '${db_name}'. Registry row ${registry_id} was not removed."
  fi
  still=$(psql_postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '${db_name}'") || still="1"
  if [ "$still" = "1" ]; then
    fail_before_drop "Database drop failed for '${db_name}'. Registry row ${registry_id} was not removed."
  fi
  # Drop is verified. Do not restore connections and do not recreate the database.
  allow_changed=0
  dropped=1
fi

# Drop has been verified, or the database was already absent. Only then remove the registry row.
if ! $COMPOSE exec -T truckerp-postgres psql -U postgres -d trucking_erp -v ON_ERROR_STOP=1 -c "
DO \$\$
DECLARE
  tid BIGINT;
  uid VARCHAR(36);
BEGIN
  SELECT id INTO tid FROM platform_tenants WHERE slug = '${slug}' AND db_name = '${db_name}' LIMIT 1;
  SELECT id INTO uid FROM platform_users WHERE email = '${email}' LIMIT 1;

  BEGIN
    DELETE FROM platform_otp_tokens WHERE email = '${email}';
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  BEGIN
    DELETE FROM reserved_slugs WHERE slug = '${slug}';
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  IF tid IS NOT NULL THEN
    DELETE FROM tenant_memberships WHERE tenant_id = tid;
    DELETE FROM platform_tenant_members WHERE tenant_id = tid;
    DELETE FROM platform_subscriptions WHERE tenant_id = tid;
    DELETE FROM platform_company_profiles WHERE tenant_id = tid;
    DELETE FROM platform_onboarding_payloads WHERE tenant_id = tid;
    BEGIN
      DELETE FROM platform_security_events WHERE tenant_id = tid;
    EXCEPTION WHEN undefined_table THEN NULL;
    END;
    DELETE FROM platform_tenants WHERE id = tid AND db_name = '${db_name}';
  END IF;

  IF uid IS NOT NULL THEN
    DELETE FROM tenant_memberships WHERE user_id = uid;
    DELETE FROM platform_tenant_members WHERE platform_user_id = uid;
    BEGIN
      DELETE FROM platform_security_events WHERE user_id = uid;
    EXCEPTION WHEN undefined_table THEN NULL;
    END;
    DELETE FROM platform_users WHERE id = uid;
  END IF;
END \$\$;
"; then
  if [ "$dropped" = "1" ]; then
    echo "Partial failure: database '${db_name}' was dropped, but platform registry deletion failed for slug '${slug}'. Registry row ${registry_id} may still exist." >&2
  else
    echo "Registry deletion failed for slug '${slug}'. Database '${db_name}' was already absent. Registry row ${registry_id} may still exist." >&2
  fi
  exit 1
fi

echo "Dropped '${db_name}' and then removed registry slug '${slug}'."
