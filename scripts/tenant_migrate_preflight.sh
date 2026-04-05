#!/usr/bin/env bash
# =============================================================================
# Tenant migrate preflight (read-only, fast).
# Run inside truckerp-api container at /app.
# Requires: ALEMBIC_TENANT_DATABASE_URL (for alembic), TENANT_DATABASE_URL
# (plain postgresql:// for psql). If only ALEMBIC_* is set, we derive
# TENANT_DATABASE_URL by stripping +asyncpg.
# Exit non-zero and print STOP banner if any check fails.
# =============================================================================
set -euo pipefail

STOP_BANNER="
========================================
  STOP — Tenant migration preflight failed
========================================
Fix the reported issue(s) before running upgrade.
Do not run 'alembic upgrade' until preflight passes.
========================================
"

git_safe_app() {
  GIT_CONFIG_COUNT=1 \
  GIT_CONFIG_KEY_0=safe.directory \
  GIT_CONFIG_VALUE_0=/app \
  git -C /app "$@"
}

# 1) Authoritative environment: we must be in container at /app
if ! [ -f /app/alembic_tenant.ini ]; then
  echo "Preflight failed: not in authoritative environment (missing /app/alembic_tenant.ini). Run inside truckerp-api container at /app."
  echo "$STOP_BANNER"
  exit 1
fi

# 2) Repo alignment (commit hash)
echo "Preflight: repo at /app"
COMMIT_APP=$(git_safe_app rev-parse --short HEAD 2>/dev/null || true)
if [ -z "$COMMIT_APP" ]; then
  echo "Preflight failed: could not get commit hash for /app."
  echo "$STOP_BANNER"
  exit 1
fi
echo "  commit (container /app): $COMMIT_APP"

# 3) Env gate: ALEMBIC_TENANT_DATABASE_URL must be set
if [ -z "${ALEMBIC_TENANT_DATABASE_URL:-}" ]; then
  echo "Preflight failed: ALEMBIC_TENANT_DATABASE_URL is not set."
  echo "$STOP_BANNER"
  exit 1
fi
echo "  ALEMBIC_TENANT_DATABASE_URL: set"

normalize_tenant_db_url_for_psql() {
  # Accepts:
  # - postgresql+asyncpg://... -> postgresql://...
  # - postgresql://...         -> (unchanged)
  # - postgres://...           -> postgresql://... (normalize for safety)
  # Also normalizes postgres+asyncpg://... for older envs.
  local url="$1"
  url="${url//+asyncpg/}"
  if [[ "$url" =~ ^postgres:// ]]; then
    url="postgresql://${url#postgres://}"
  fi
  echo "$url"
}

# TENANT_DATABASE_URL for psql (plain postgresql://). If not set, derive it.
if [ -n "${TENANT_DATABASE_URL:-}" ]; then
  TENANT_DATABASE_URL="$(normalize_tenant_db_url_for_psql "$TENANT_DATABASE_URL")"
else
  TENANT_DATABASE_URL="$(normalize_tenant_db_url_for_psql "$ALEMBIC_TENANT_DATABASE_URL")"
fi
export TENANT_DATABASE_URL

if [[ ! "$TENANT_DATABASE_URL" =~ ^postgresql:// ]]; then
  echo "Preflight failed: TENANT_DATABASE_URL must start with postgresql:// (got: $TENANT_DATABASE_URL)."
  echo "$STOP_BANNER"
  exit 1
fi
echo "  TENANT_DATABASE_URL: set (for psql)"

# DB target sanity (prevents wrong-DB accidents)
PSQL_OPTS=(-v ON_ERROR_STOP=1 -X -q -t -A)
TENANT_DB_NAME="$(psql "$TENANT_DATABASE_URL" "${PSQL_OPTS[@]}" -c "select current_database();")"
if [ -z "${TENANT_DB_NAME:-}" ]; then
  echo "Preflight failed: could not determine tenant DB name via 'select current_database();'."
  echo "$STOP_BANNER"
  exit 1
fi
echo "Tenant DB target: $TENANT_DB_NAME"

# 4) Exactly one tenant Alembic head (hard-stop on alembic heads error)
HEADS_OUT=""
if ! HEADS_OUT="$(cd /app && alembic -c alembic_tenant.ini heads 2>&1)"; then
  echo "Preflight failed: alembic heads command failed."
  echo "$HEADS_OUT"
  echo "$STOP_BANNER"
  exit 1
fi

HEAD_COUNT=$(printf "%s\n" "$HEADS_OUT" | grep -c '(head)')
if [ "${HEAD_COUNT:-0}" -ne 1 ]; then
  echo "Preflight failed: tenant Alembic must have exactly one head (got: $HEAD_COUNT). Create a merge revision."
  echo "$HEADS_OUT"
  echo "$STOP_BANNER"
  exit 1
fi
echo "  tenant heads: 1"

# 5) Critical read-only safety checks (psql)
run_count() {
  psql "$TENANT_DATABASE_URL" "${PSQL_OPTS[@]}" -c "$1"
}

FAILED=0

# Orphan rows: driver_profiles -> people
C=$(run_count "select count(*) from public.driver_profiles dp left join public.people p on p.tenant_id = dp.tenant_id and p.id = dp.person_id where dp.person_id is not null and p.id is null")
if [ "${C:-0}" -ne 0 ]; then
  echo "Preflight failed: orphan rows driver_profiles->people = $C (must be 0)."
  FAILED=1
fi

# Orphan rows: person_roles -> people
C=$(run_count "select count(*) from public.person_roles pr left join public.people p on p.tenant_id = pr.tenant_id and p.id = pr.person_id where pr.person_id is not null and p.id is null")
if [ "${C:-0}" -ne 0 ]; then
  echo "Preflight failed: orphan rows person_roles->people = $C (must be 0)."
  FAILED=1
fi

# Orphan rows: drivers -> people (if drivers exists)
C=$(run_count "select count(*) from public.drivers d left join public.people p on p.tenant_id = d.tenant_id and p.id = d.person_id where d.person_id is not null and p.id is null")
if [ "${C:-0}" -ne 0 ]; then
  echo "Preflight failed: orphan rows drivers->people = $C (must be 0)."
  FAILED=1
fi

# Cross-tenant: driver_profiles -> people
C=$(run_count "select count(*) from public.driver_profiles dp join public.people p on p.id = dp.person_id where dp.tenant_id <> p.tenant_id")
if [ "${C:-0}" -ne 0 ]; then
  echo "Preflight failed: cross-tenant mismatches driver_profiles->people = $C (must be 0)."
  FAILED=1
fi

# Cross-tenant: person_roles -> people
C=$(run_count "select count(*) from public.person_roles pr join public.people p on p.id = pr.person_id where pr.tenant_id <> p.tenant_id")
if [ "${C:-0}" -ne 0 ]; then
  echo "Preflight failed: cross-tenant mismatches person_roles->people = $C (must be 0)."
  FAILED=1
fi

# Cross-tenant: drivers -> people
C=$(run_count "select count(*) from public.drivers d join public.people p on p.id = d.person_id where d.tenant_id <> p.tenant_id")
if [ "${C:-0}" -ne 0 ]; then
  echo "Preflight failed: cross-tenant mismatches drivers->people = $C (must be 0)."
  FAILED=1
fi

# FKs referencing people that do NOT include tenant_id (B19 style; include ref_table in CTE)
FK_BAD=$(psql "$TENANT_DATABASE_URL" "${PSQL_OPTS[@]}" -c "
with fk_cols as (
  select
    con.conname as fk_name,
    rel.relname as table_name,
    rel2.relname as ref_table,
    array_agg(a.attname order by ck.ord) as cols,
    array_agg(a2.attname order by ck.ord) as ref_cols
  from pg_constraint con
  join pg_class rel on rel.oid = con.conrelid
  join pg_class rel2 on rel2.oid = con.confrelid
  join pg_namespace nsp on nsp.oid = rel.relnamespace
  join unnest(con.conkey) with ordinality as ck(attnum, ord) on true
  join pg_attribute a on a.attrelid = rel.oid and a.attnum = ck.attnum
  join unnest(con.confkey) with ordinality as fk(attnum, ord) on fk.ord = ck.ord
  join pg_attribute a2 on a2.attrelid = rel2.oid and a2.attnum = fk.attnum
  where con.contype='f' and nsp.nspname='public'
  group by con.oid, con.conname, rel.relname, rel2.relname
)
select count(*) from fk_cols where ref_table='people' and not ('tenant_id' = any(cols) and 'tenant_id' = any(ref_cols));
")
if [ "${FK_BAD:-0}" -ne 0 ]; then
  echo "Preflight failed: FKs referencing people that do NOT include tenant_id = $FK_BAD (must be 0)."
  FAILED=1
fi

# Critical NULL checks (B16 subset)
NULL_PEOPLE=$(run_count "select count(*) from public.people where tenant_id is null or id is null")
if [ "${NULL_PEOPLE:-0}" -ne 0 ]; then
  echo "Preflight failed: people.tenant_id or people.id NULL rows = $NULL_PEOPLE (must be 0)."
  FAILED=1
fi
NULL_DP=$(run_count "select count(*) from public.driver_profiles where tenant_id is null or id is null or person_id is null")
if [ "${NULL_DP:-0}" -ne 0 ]; then
  echo "Preflight failed: driver_profiles critical NULL rows = $NULL_DP (must be 0)."
  FAILED=1
fi
NULL_PR=$(run_count "select count(*) from public.person_roles where tenant_id is null or id is null or person_id is null")
if [ "${NULL_PR:-0}" -ne 0 ]; then
  echo "Preflight failed: person_roles critical NULL rows = $NULL_PR (must be 0)."
  FAILED=1
fi

# NOT VALID constraints (B30)
NOT_VALID=$(psql "$TENANT_DATABASE_URL" "${PSQL_OPTS[@]}" -c "select count(*) from pg_constraint where convalidated = false")
if [ "${NOT_VALID:-0}" -ne 0 ]; then
  echo "Preflight failed: NOT VALID constraints = $NOT_VALID (must be 0)."
  FAILED=1
fi

if [ "$FAILED" -ne 0 ]; then
  echo "$STOP_BANNER"
  exit 1
fi

echo "Preflight: all checks passed."
