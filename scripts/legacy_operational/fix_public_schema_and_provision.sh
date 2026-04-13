#!/usr/bin/env bash
# =============================================================================
# LEGACY — ARCHIVED — DO NOT USE FOR CURRENT PRODUCTION (Docker + SSM)
# =============================================================================
# Former repo-root script; kept under scripts/legacy_operational/ for archaeology
# only. It does NOT match the standard TruckERP production model:
#   - Defaults (e.g. PG_CONTAINER=shared-postgres, .env-based PLATFORM_DB) are
#     not the compose service truckerp-postgres / platform DB trucking_erp.
#   - API + secrets: use Docker + SSM paths above, not ad-hoc localhost provision
#     against an unknown stack.
#
# Probes tenant registry via guessed table/column names and may drive provision;
# high blast radius — read fully before any use.
# =============================================================================

set -euo pipefail

TENANT_ID="${TENANT_ID:-1}"
PG_CONTAINER="${PG_CONTAINER:-shared-postgres}"
PG_SUPERUSER="${PG_SUPERUSER:-postgres}"

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
PROVISION_PATH="/api/v1/platform/tenants/${TENANT_ID}/provision"

# Try to infer platform DB name from .env DATABASE_URL (path after last '/')
PLATFORM_DB="${PLATFORM_DB:-}"
if [[ -z "${PLATFORM_DB}" && -f .env ]]; then
  PLATFORM_DB="$(grep -E '^DATABASE_URL=' .env | head -n1 | sed 's/^DATABASE_URL=//' | sed -E 's/\?.*$//' | awk -F/ '{print $NF}')"
fi
PLATFORM_DB="${PLATFORM_DB:-postgres}"

psql_in() {
  local db="$1"
  local sql="$2"
  docker exec -i "${PG_CONTAINER}" psql -U "${PG_SUPERUSER}" -d "${db}" -v ON_ERROR_STOP=1 -t -A -c "${sql}"
}

echo "== Checking Postgres container: ${PG_CONTAINER}"
if ! docker ps --format '{{.Names}}' | grep -qx "${PG_CONTAINER}"; then
  echo "ERROR: Container '${PG_CONTAINER}' is not running. Run: docker start ${PG_CONTAINER}"
  exit 1
fi

echo "== Using PLATFORM_DB='${PLATFORM_DB}'"
echo "== Finding candidate tenant registry tables (any schema)..."

# Find tables that have tenant-ish columns (db name/user/url)
candidates="$(
psql_in "${PLATFORM_DB}" "
SELECT DISTINCT table_schema || '.' || table_name
FROM information_schema.columns
WHERE (table_name ILIKE '%tenant%' OR table_name ILIKE '%tenants%')
  AND (
    column_name ILIKE '%db%name%' OR
    column_name ILIKE '%db%user%' OR
    column_name ILIKE '%db%url%'  OR
    column_name ILIKE '%database%name%' OR
    column_name ILIKE '%database%user%' OR
    column_name ILIKE '%database%url%'
  )
ORDER BY 1;"
)"

if [[ -z "${candidates}" ]]; then
  echo "ERROR: No tenant-like registry tables found in DB '${PLATFORM_DB}'."
  echo "Quick manual check: docker exec -it ${PG_CONTAINER} psql -U ${PG_SUPERUSER} -d ${PLATFORM_DB}"
  echo "Then run: \\dt *.*"
  exit 1
fi

echo "== Candidates:"
echo "${candidates}" | sed 's/^/  - /'

TENANT_DB_NAME=""
TENANT_DB_USER=""
TENANT_DB_URL=""

pick_first_existing_col() {
  local db="$1" schema="$2" table="$3"
  shift 3
  local cols
  cols="$(psql_in "${db}" "SELECT column_name FROM information_schema.columns WHERE table_schema='${schema}' AND table_name='${table}'")"
  for c in "$@"; do
    if printf "%s\n" "${cols}" | grep -qx "${c}"; then
      echo "${c}"
      return 0
    fi
  done
  echo ""
}

echo "== Searching tenant row for TENANT_ID=${TENANT_ID} ..."
while IFS= read -r full; do
  [[ -z "${full}" ]] && continue
  schema="${full%%.*}"
  table="${full#*.}"

  # identify likely columns
  dbname_col="$(pick_first_existing_col "${PLATFORM_DB}" "${schema}" "${table}" tenant_db_name db_name database_name tenant_database tenant_db dbname)"
  dbuser_col="$(pick_first_existing_col "${PLATFORM_DB}" "${schema}" "${table}" tenant_db_user db_user database_user db_username username user_name)"
  dburl_col="$(pick_first_existing_col  "${PLATFORM_DB}" "${schema}" "${table}" tenant_db_url database_url db_url tenant_database_url tenant_url)"

  id_col="$(pick_first_existing_col "${PLATFORM_DB}" "${schema}" "${table}" id tenant_id)"

  # must have at least one useful column and an identifier column
  if [[ -z "${id_col}" ]]; then
    continue
  fi
  if [[ -z "${dbname_col}" && -z "${dbuser_col}" && -z "${dburl_col}" ]]; then
    continue
  fi

  # build select list
  select_list="${id_col}"
  [[ -n "${dbname_col}" ]] && select_list+=",${dbname_col}"
  [[ -n "${dbuser_col}" ]] && select_list+=",${dbuser_col}"
  [[ -n "${dburl_col}"  ]] && select_list+=",${dburl_col}"

  # Try to fetch row
  row="$(psql_in "${PLATFORM_DB}" "SELECT ${select_list} FROM \"${schema}\".\"${table}\" WHERE \"${id_col}\"=${TENANT_ID} LIMIT 1;")" || row=""

  if [[ -n "${row}" ]]; then
    echo "== FOUND in ${schema}.${table} (key=${id_col})"
    IFS='|' read -r _k _a _b _c <<< "${row}"

    # Map values based on which cols were included (order matters)
    vals=()
    [[ -n "${dbname_col}" ]] && vals+=("DBNAME")
    [[ -n "${dbuser_col}" ]] && vals+=("DBUSER")
    [[ -n "${dburl_col}"  ]] && vals+=("DBURL")

    # _a/_b/_c align with vals[0..]
    for i in "${!vals[@]}"; do
      v="${_a}"
      [[ "${i}" -eq 1 ]] && v="${_b}"
      [[ "${i}" -eq 2 ]] && v="${_c}"
      case "${vals[$i]}" in
        DBNAME) TENANT_DB_NAME="${v}" ;;
        DBUSER) TENANT_DB_USER="${v}" ;;
        DBURL)  TENANT_DB_URL="${v}" ;;
      esac
    done
    break
  fi
done <<< "${candidates}"

if [[ -z "${TENANT_DB_NAME}" && -n "${TENANT_DB_URL}" ]]; then
  TENANT_DB_NAME="$(python3 - <<'PY'
import os, re
u=os.environ.get("TENANT_DB_URL","")
m=re.search(r"/([^/?#]+)$", u)
print(m.group(1) if m else "")
PY
)"
fi

if [[ -z "${TENANT_DB_USER}" && -n "${TENANT_DB_URL}" ]]; then
  TENANT_DB_USER="$(python3 - <<'PY'
import os, re, urllib.parse
u=os.environ.get("TENANT_DB_URL","")
m=re.search(r"//([^:/@]+)(?::[^@]*)?@", u)
print(urllib.parse.unquote(m.group(1)) if m else "")
PY
)"
fi

echo "== Extracted:"
echo "   TENANT_DB_NAME='${TENANT_DB_NAME}'"
echo "   TENANT_DB_USER='${TENANT_DB_USER}'"
[[ -n "${TENANT_DB_URL}" ]] && echo "   TENANT_DB_URL='${TENANT_DB_URL}'"

if [[ -z "${TENANT_DB_NAME}" || -z "${TENANT_DB_USER}" ]]; then
  echo "ERROR: Could not determine TENANT_DB_NAME and TENANT_DB_USER."
  echo "Open psql and inspect the found table row manually."
  exit 1
fi

echo "== Fixing public schema privileges on tenant DB..."
psql_in "${TENANT_DB_NAME}" "ALTER SCHEMA public OWNER TO \"${TENANT_DB_USER}\";"
psql_in "${TENANT_DB_NAME}" "GRANT USAGE, CREATE ON SCHEMA public TO \"${TENANT_DB_USER}\";"

echo "== Retrying provisioning: POST ${API_BASE}${PROVISION_PATH}"
curl -sS -i -X POST "${API_BASE}${PROVISION_PATH}"
echo
echo "== Finished."
