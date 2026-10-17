#!/bin/sh
# Decision helpers for tools/reset_signup.sh. Sourced by that script.
# These functions do not connect to PostgreSQL.

reset_signup_refuse() {
  printf '%s\n' "$1" >&2
  exit 1
}

reset_signup_validate_slug() {
  printf '%s' "$1" | grep -Eq '^[a-z0-9][a-z0-9-]{0,62}$' \
    || reset_signup_refuse "Refusing slug. Expected a lowercase workspace slug."
}

reset_signup_validate_db_name() {
  printf '%s' "$1" | grep -Eq '^tenant_[a-z0-9_]+$' \
    || reset_signup_refuse "Refusing database name. Expected tenant_<slug>."
}

reset_signup_validate_email() {
  printf '%s' "$1" | grep -Eq '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' \
    || reset_signup_refuse "Refusing email."
}

# demo and ikl are protected even when RESET_SIGNUP_ALLOW_ACTIVE names them.
reset_signup_assert_not_protected() {
  slug="$1"
  db_name="$2"
  case "$slug" in
    demo|ikl)
      reset_signup_refuse "Refusing protected production tenant slug '${slug}'."
      ;;
  esac
  case "$db_name" in
    tenant_demo|tenant_ikl)
      reset_signup_refuse "Refusing protected production tenant database '${db_name}'."
      ;;
  esac
}

# Active tenants stay protected unless the operator names that exact slug.
reset_signup_assert_active_allowed() {
  slug="$1"
  status="$2"
  allow="${3:-}"
  if [ "$status" = "ACTIVE" ] && [ "$allow" != "$slug" ]; then
    reset_signup_refuse "Refusing active tenant '${slug}'. Set RESET_SIGNUP_ALLOW_ACTIVE=${slug} to identify it explicitly. demo and ikl stay protected."
  fi
}
