#!/bin/sh
# Reset (remove) a workspace and its owner user from the platform DB and drop the tenant DB.
# Usage: ./tools/reset_signup.sh <slug> <email>
# Example: ./tools/reset_signup.sh demo user@example.com
#
# Run from repo root. Uses same compose as API (-f docker-compose.yml -f docker-compose.dev.yml).
# Platform DB (trucking_erp): removes tenant, user, memberships, subscriptions,
# onboarding payloads, OTP tokens, security events, and reserved_slugs.
# Then drops the tenant database (tenant_<slug>).

set -eu

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <slug> <email>" >&2
  exit 1
fi

slug="$1"
email="$2"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

# Platform DB: delete in FK-safe order. Tables must match current schema.
# - tenant_memberships, platform_tenant_members: link user ↔ tenant
# - platform_onboarding_payloads, platform_subscriptions, platform_company_profiles: tenant children
# - platform_otp_tokens, platform_security_events: by email/user_id/tenant_id
# - reserved_slugs: optional (may not exist)
# - Then tenant, then user.
$COMPOSE exec -T truckerp-postgres psql -U postgres -d trucking_erp -c "
DO \$\$
DECLARE
  tid BIGINT;
  uid VARCHAR(36);
BEGIN
  SELECT id INTO tid FROM platform_tenants WHERE slug = '${slug}' LIMIT 1;
  SELECT id INTO uid FROM platform_users WHERE email = '${email}' LIMIT 1;

  -- OTP tokens for this email (table may not exist in all envs)
  BEGIN
    DELETE FROM platform_otp_tokens WHERE email = '${email}';
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  -- Reserved slug (table may not exist)
  BEGIN
    DELETE FROM reserved_slugs WHERE slug = '${slug}';
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  -- Tenant and its children (order matters for FKs)
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
    DELETE FROM platform_tenants WHERE id = tid;
  END IF;

  -- User and remaining references
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
"

# Drop tenant DB (terminate connections first)
safe_slug=$(printf "%s" "$slug" | tr -c 'a-zA-Z0-9_' '_' | tr 'A-Z' 'a-z')
db_name="tenant_${safe_slug}"
$COMPOSE exec -T truckerp-postgres psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${db_name}' AND pid <> pg_backend_pid();" 2>/dev/null || true
$COMPOSE exec -T truckerp-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS \"${db_name}\";"

echo "Done. Removed workspace '${slug}' and user '${email}' (if present). Slug '${slug}' is now available for signup."
