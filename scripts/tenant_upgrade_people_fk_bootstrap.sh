#!/usr/bin/env bash
# =============================================================================
# Bootstrap the people composite-FK hardening revision that allows the normal
# tenant migration wrapper preflight to pass. Use only for the known case where
# the preflight fails solely because legacy people FKs do not include tenant_id.
# Must be run inside truckerp-api container at /app.
# =============================================================================
set -euo pipefail

TARGET_REVISION="c3d4e5f6a7b8"
STOP_BANNER="
========================================
  STOP — People FK bootstrap failed
========================================
Fix the reported issue(s) before running the bootstrap migration.
After success, rerun scripts/tenant_upgrade_head.sh normally.
========================================
"

git_safe_app() {
  GIT_CONFIG_COUNT=1 \
  GIT_CONFIG_KEY_0=safe.directory \
  GIT_CONFIG_VALUE_0=/app \
  git -C /app "$@"
}

if ! [ -f /app/alembic_tenant.ini ]; then
  echo "Bootstrap failed: not in authoritative environment (/app missing alembic_tenant.ini)."
  echo "$STOP_BANNER"
  exit 1
fi

echo "Bootstrap: repo at /app"
COMMIT_APP="$(git_safe_app rev-parse --short HEAD 2>/dev/null || true)"
if [ -z "$COMMIT_APP" ]; then
  echo "Bootstrap failed: could not get commit hash for /app."
  echo "$STOP_BANNER"
  exit 1
fi
echo "  commit (container /app): $COMMIT_APP"

if [ -z "${ALEMBIC_TENANT_DATABASE_URL:-}" ]; then
  echo "Bootstrap failed: ALEMBIC_TENANT_DATABASE_URL is not set."
  echo "$STOP_BANNER"
  exit 1
fi
echo "  ALEMBIC_TENANT_DATABASE_URL: set"

normalize_tenant_db_url_for_psql() {
  local url="$1"
  url="${url//+asyncpg/}"
  if [[ "$url" =~ ^postgres:// ]]; then
    url="postgresql://${url#postgres://}"
  fi
  echo "$url"
}

TENANT_DATABASE_URL="$(normalize_tenant_db_url_for_psql "${TENANT_DATABASE_URL:-$ALEMBIC_TENANT_DATABASE_URL}")"
export TENANT_DATABASE_URL

if [[ ! "$TENANT_DATABASE_URL" =~ ^postgresql:// ]]; then
  echo "Bootstrap failed: TENANT_DATABASE_URL must start with postgresql:// (got: $TENANT_DATABASE_URL)."
  echo "$STOP_BANNER"
  exit 1
fi
echo "  TENANT_DATABASE_URL: set (for psql)"

PSQL_OPTS=(-v ON_ERROR_STOP=1 -X -q -t -A)
TENANT_DB_NAME="$(psql "$TENANT_DATABASE_URL" "${PSQL_OPTS[@]}" -c "select current_database();")"
if [ -z "${TENANT_DB_NAME:-}" ]; then
  echo "Bootstrap failed: could not determine tenant DB name."
  echo "$STOP_BANNER"
  exit 1
fi
echo "Tenant DB target: $TENANT_DB_NAME"

HEADS_OUT=""
if ! HEADS_OUT="$(cd /app && alembic -c alembic_tenant.ini heads 2>&1)"; then
  echo "Bootstrap failed: alembic heads command failed."
  echo "$HEADS_OUT"
  echo "$STOP_BANNER"
  exit 1
fi
HEAD_COUNT=$(printf "%s\n" "$HEADS_OUT" | grep -c '(head)')
if [ "${HEAD_COUNT:-0}" -ne 1 ]; then
  echo "Bootstrap failed: tenant Alembic must have exactly one head (got: $HEAD_COUNT)."
  echo "$HEADS_OUT"
  echo "$STOP_BANNER"
  exit 1
fi
echo "  tenant heads: 1"

EXPECTED_FKS=$'driver_profiles_person_id_fkey\ndriver_profiles\n{person_id}\n{id}\n'\
$'fk_drivers_person_id_people\ndrivers\n{person_id}\n{id}\n'\
$'person_roles_person_id_fkey\nperson_roles\n{person_id}\n{id}'

ACTUAL_FKS="$(python3 - <<'PY'
import os
import psycopg2

url = os.environ["TENANT_DATABASE_URL"]
query = """
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
select fk_name, table_name, cols::text, ref_cols::text
from fk_cols
where ref_table='people' and not ('tenant_id' = any(cols) and 'tenant_id' = any(ref_cols))
order by table_name, fk_name
"""
with psycopg2.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            for value in row:
                print(value)
PY
)"

if [ "$ACTUAL_FKS" != "$EXPECTED_FKS" ]; then
  echo "Bootstrap failed: unexpected people-FK drift detected."
  echo "Expected exactly these legacy FKs:"
  printf '%s\n' "$EXPECTED_FKS"
  echo "Actual:"
  printf '%s\n' "$ACTUAL_FKS"
  echo "$STOP_BANNER"
  exit 1
fi
echo "  people FK drift matches expected legacy trio"

run_count() {
  psql "$TENANT_DATABASE_URL" "${PSQL_OPTS[@]}" -c "$1"
}

FAILED=0

check_zero() {
  local label="$1"
  local sql="$2"
  local count
  count="$(run_count "$sql")"
  if [ "${count:-0}" -ne 0 ]; then
    echo "Bootstrap failed: $label = $count (must be 0)."
    FAILED=1
  fi
}

check_zero "orphan rows driver_profiles->people" "select count(*) from public.driver_profiles dp left join public.people p on p.tenant_id = dp.tenant_id and p.id = dp.person_id where dp.person_id is not null and p.id is null"
check_zero "orphan rows person_roles->people" "select count(*) from public.person_roles pr left join public.people p on p.tenant_id = pr.tenant_id and p.id = pr.person_id where pr.person_id is not null and p.id is null"
check_zero "orphan rows drivers->people" "select count(*) from public.drivers d left join public.people p on p.tenant_id = d.tenant_id and p.id = d.person_id where d.person_id is not null and p.id is null"
check_zero "cross-tenant mismatches driver_profiles->people" "select count(*) from public.driver_profiles dp join public.people p on p.id = dp.person_id where dp.tenant_id <> p.tenant_id"
check_zero "cross-tenant mismatches person_roles->people" "select count(*) from public.person_roles pr join public.people p on p.id = pr.person_id where pr.tenant_id <> p.tenant_id"
check_zero "cross-tenant mismatches drivers->people" "select count(*) from public.drivers d join public.people p on p.id = d.person_id where d.tenant_id <> p.tenant_id"
check_zero "people critical NULL rows" "select count(*) from public.people where tenant_id is null or id is null"
check_zero "driver_profiles critical NULL rows" "select count(*) from public.driver_profiles where tenant_id is null or id is null or person_id is null"
check_zero "person_roles critical NULL rows" "select count(*) from public.person_roles where tenant_id is null or id is null or person_id is null"
check_zero "NOT VALID constraints" "select count(*) from pg_constraint where convalidated = false"

if [ "$FAILED" -ne 0 ]; then
  echo "$STOP_BANNER"
  exit 1
fi

echo "Bootstrap: non-structural checks passed."
echo "Running: alembic -c /app/alembic_tenant.ini upgrade $TARGET_REVISION"
cd /app && alembic -c /app/alembic_tenant.ini upgrade "$TARGET_REVISION"
echo "Bootstrap migration completed."
