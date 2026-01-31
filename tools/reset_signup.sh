#!/bin/sh
set -eu

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <slug> <email>" >&2
  exit 1
fi

slug="$1"
email="$2"

docker compose exec -T truckerp-postgres psql -U postgres -d trucking_erp -c "DO \$\$ DECLARE tid BIGINT; uid VARCHAR; BEGIN SELECT id INTO tid FROM platform_tenants WHERE slug='${slug}'; SELECT id INTO uid FROM platform_users WHERE email='${email}'; DELETE FROM signup_otp_tokens WHERE email='${email}'; DELETE FROM slug_reservations WHERE slug='${slug}'; DELETE FROM platform_workspace_claims WHERE slug='${slug}' OR email='${email}'; DELETE FROM platform_otp_tokens WHERE email='${email}'; IF tid IS NOT NULL THEN DELETE FROM platform_tenant_members WHERE tenant_id = tid; DELETE FROM platform_subscriptions WHERE tenant_id = tid; DELETE FROM platform_company_profiles WHERE tenant_id = tid; DELETE FROM platform_security_events WHERE tenant_id = tid; DELETE FROM platform_tenants WHERE id = tid; END IF; IF uid IS NOT NULL THEN DELETE FROM platform_tenant_members WHERE platform_user_id = uid; DELETE FROM platform_security_events WHERE email='${email}'; DELETE FROM platform_users WHERE id = uid; END IF; END \$\$;"

safe_slug=$(printf "%s" "$slug" | tr -c 'a-zA-Z0-9_' '_' | tr 'A-Z' 'a-z')
db_name="tenant_${safe_slug}"
docker compose exec -T truckerp-postgres psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${db_name}';"
docker compose exec -T truckerp-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS \"${db_name}\";"

echo "done"
