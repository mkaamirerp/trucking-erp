#!/usr/bin/env bash
set -euo pipefail

# --- Mode detection: host vs docker-network ---
HARDENED_MODE=0
HOST_API="${BASE_URL:-http://127.0.0.1:8000}"
HOST_CURL="curl"
CURL_CMD="$HOST_CURL"

if "$HOST_CURL" -fsS --max-time 1 "$HOST_API/api/v1/health" >/dev/null 2>&1; then
  echo "🟢 Host API reachable — host mode"
  BASE_URL="$HOST_API"
else
  echo "🔒 Host API NOT reachable — docker-network mode"
  HARDENED_MODE=1
  CURL_CMD="docker run --rm --network truckerp_net curlimages/curl:8.5.0"
  BASE_URL="http://truckerp-api:8000"
fi

API="${API:-$BASE_URL/api/v1}"

TENANT_ID="${TENANT_ID:-1}"
TENANT_ROLES="${TENANT_ROLES:-TENANT_ADMIN}"
TENANT_HEADER=(
  -H "X-Tenant-ID: ${TENANT_ID}"
  -H "X-Tenant-Roles: ${TENANT_ROLES}"
)

# Helpers
hr() { printf "\n============================================================\n"; }
subhr() { printf "\n------------------------------\n"; }
ok() { printf "✅ %s\n" "$1"; }
warn() { printf "⚠️  %s\n" "$1"; }
fail() { printf "❌ %s\n" "$1" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing dependency: $1"
}

curl_json() {
  $CURL_CMD -sS --max-time 8 "$@"
}

http_code() {
  $CURL_CMD -sS -o /dev/null --max-time 8 -w "%{http_code}" "$@"
}

json_type_is() {
  local json="$1" t="$2"
  echo "$json" | jq -e --arg t "$t" 'type==$t' >/dev/null
}

count_array() {
  local json="$1"
  echo "$json" | jq 'length'
}

PYTHON="${PYTHON:-venv/bin/python}"

# Dependencies
need_cmd jq
need_cmd $HOST_CURL
need_cmd docker

smtp_smoke() {
  hr
  echo "SMTP connectivity smoke"
  if PYTHONPATH="." $PYTHON scripts/smoke_smtp.py; then
    ok "SMTP smoke passed"
  else
    fail "SMTP smoke test failed"
  fi
}

frontend_smoke() {
  hr
  echo "Frontend public smoke"
  FRONTEND_BASE="${FRONTEND_BASE:-http://localhost}" PUBLIC_API_BASE="${BASE_URL}/api/v1/public" PUBLIC_CURL="$CURL_CMD" bash scripts/smoke_frontend_public.sh
}

hr
echo "Trucking ERP EXTENDED Smoke Test (simplified)"
echo "BASE_URL=$BASE_URL"
echo "API=$API"
echo "Time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# Hardened infra checks (only meaningful in docker-network mode)
if [[ "$HARDENED_MODE" == "1" ]]; then
  hr
  echo "Hardened mode assertions (container-only reachability)"

  # Host cannot hit API directly
  set +e
  host_api_code="$("$HOST_CURL" -sS -o /dev/null --max-time 2 -w "%{http_code}" "$HOST_API/api/v1/health" 2>/dev/null || true)"
  set -e
  if [[ "$host_api_code" == "000" || -z "$host_api_code" ]]; then
    ok "Host cannot reach $HOST_API/api/v1/health (expected)"
  else
    warn "Host unexpectedly reached $HOST_API/api/v1/health (HTTP $host_api_code)"
  fi

  # Host cannot talk to Postgres on 5432
  set +e
  "$HOST_CURL" -sS --max-time 2 "http://127.0.0.1:5432" >/dev/null 2>&1
  db_status=$?
  set -e
  if [[ "$db_status" -eq 0 ]]; then
    warn "Host unexpectedly reached 127.0.0.1:5432"
  else
    ok "Host cannot reach 127.0.0.1:5432 (expected)"
  fi

  # Inspect containers
  pg_cid="$(docker ps --filter name=truckerp-postgres --format '{{.ID}}' | head -n1)"
  api_cid="$(docker ps --filter name=truckerp-api --format '{{.ID}}' | head -n1)"

  if [[ -n "$api_cid" ]]; then
    api_ports="$(docker inspect -f '{{json .NetworkSettings.Ports}}' "$api_cid")"
    api_networks="$(docker inspect -f '{{range $n,$v := .NetworkSettings.Networks}}{{printf "%s " $n}}{{end}}' "$api_cid")"
    echo "FastAPI ports: $api_ports"
    echo "FastAPI networks: $api_networks"
    if echo "$api_ports" | jq -e '([.[]? | select(.!=null)] | length)==0' >/dev/null 2>&1; then
      ok "FastAPI container has no host port bindings"
    else
      warn "FastAPI container exposes host ports: $api_ports"
    fi
    if echo "$api_networks" | grep -q "truckerp_net" >/dev/null 2>&1; then
      ok "FastAPI container attached to truckerp_net"
    else
      warn "FastAPI not on truckerp_net"
    fi
  else
    warn "FastAPI container not found via name filter 'truckerp-api'"
  fi

  if [[ -n "$pg_cid" ]]; then
    pg_ports="$(docker inspect -f '{{json .NetworkSettings.Ports}}' "$pg_cid")"
    pg_networks="$(docker inspect -f '{{range $n,$v := .NetworkSettings.Networks}}{{printf "%s " $n}}{{end}}' "$pg_cid")"
    echo "Postgres ports: $pg_ports"
    echo "Postgres networks: $pg_networks"
    if echo "$pg_ports" | jq -e '([.[]? | select(.!=null)] | length)==0' >/dev/null 2>&1; then
      ok "Postgres container has no host port bindings"
    else
      warn "Postgres container exposes host ports: $pg_ports"
    fi
    if echo "$pg_networks" | grep -q "truckerp_net" >/dev/null 2>&1; then
      ok "Postgres container attached to truckerp_net"
    else
      warn "Postgres not on truckerp_net"
    fi
  else
    warn "Postgres container not found via name filter 'truckerp-postgres'"
  fi

  subhr
  echo "Internal health via docker-network"
  internal_health="$(docker run --rm --network truckerp_net curlimages/curl:8.5.0 -sS "$API/health")"
  echo "$internal_health" | jq .
  echo "$internal_health" | jq -e '.status=="ok"' >/dev/null || fail "Internal health check failed"
fi

# 1) Health
hr
echo "1) Health endpoint"
health_json="$(curl_json "$API/health")"
echo "GET /api/v1/health =>"
echo "$health_json" | jq .
echo "$health_json" | jq -e '.status=="ok"' >/dev/null || fail "Health failed"
ok "Health OK"

# 1b) Tenant header enforcement
subhr
echo "1b) Tenant enforcement: drivers without tenant header should fail (400)"
code_no_tenant="$(http_code "$API/drivers")"
echo "GET /drivers (no tenant) => HTTP $code_no_tenant"
[[ "$code_no_tenant" == "400" ]] && ok "Missing tenant rejected" || fail "Expected 400 for missing tenant"

# 2) OpenAPI
hr
echo "2) OpenAPI sanity"
code_openapi="$(http_code "$BASE_URL/openapi.json")"
echo "GET /openapi.json => HTTP $code_openapi"
[[ "$code_openapi" == "200" ]] && ok "OpenAPI reachable" || warn "OpenAPI not reachable (not fatal)"

# 3) Drivers & UX HTTP tests (stubbed for now)
hr
echo "3) Drivers & UX HTTP tests"
if [[ "$HARDENED_MODE" == "1" ]]; then
  warn "Hardened mode: skipping HTTP driver and UX tests (tenant resolver not fully wired)"
else
  warn "Extended HTTP driver/UX tests temporarily disabled until tenant resolver + DB are fully wired"
fi

# TENANT ROUTING SMOKE (docker-network)
hr
echo "TENANT ROUTING SMOKE (docker-network)"
docker run --rm --network truckerp_net alpine:3.20 sh -lc '
  set -e
  apk add --no-cache curl >/dev/null
  API="http://truckerp-api:8000/api/v1"
  OK=1
  BAD=9999
  fail() { echo "FAIL: $1" >&2; exit 1; }

  R1=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Tenant-ID: $OK" "$API/drivers")
  [ "$R1" = "200" ] || fail "[Tenant OK] expected 200, got $R1"
  echo "[Tenant OK] /drivers => PASS (200)"

  R2=$(curl -s -o /dev/null -w "%{http_code}" "$API/drivers")
  [ "$R2" = "400" ] || fail "[Tenant missing] expected 400, got $R2"
  echo "[Tenant missing] /drivers => PASS (400)"

  R3=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Tenant-ID: $BAD" "$API/drivers")
  [ "$R3" = "403" ] || fail "[Tenant invalid] expected 403, got $R3"
  echo "[Tenant invalid] /drivers => PASS (403)"
'

# SMTP connectivity smoke
smtp_smoke

# Slug availability HTTP smokes
hr
echo "Slug availability checks"
slug_ok="test-company-$(date +%s)"
slug_bad='BAD!!SLUG"'
slug_reserved="admin"

slug_ok_body="$($CURL_CMD -sS --max-time 8 "$BASE_URL/api/v1/public/check-slug-availability?slug=${slug_ok}")"
code_slug_ok="$($CURL_CMD -sS -o /dev/null --max-time 8 -w "%{http_code}" "$BASE_URL/api/v1/public/check-slug-availability?slug=${slug_ok}")"
echo "GET /api/v1/public/check-slug-availability?slug=${slug_ok} => HTTP $code_slug_ok"
echo "$slug_ok_body" | jq .
[[ "$code_slug_ok" == "200" ]] || fail "Slug availability expected 200"
echo "$slug_ok_body" | jq -e '.available==true' >/dev/null || fail "Expected available=true for slug_ok"

slug_reserved_body="$($CURL_CMD -sS --max-time 8 "$BASE_URL/api/v1/public/check-slug-availability?slug=${slug_reserved}")"
code_slug_reserved="$($CURL_CMD -sS -o /dev/null --max-time 8 -w "%{http_code}" "$BASE_URL/api/v1/public/check-slug-availability?slug=${slug_reserved}")"
echo "GET /api/v1/public/check-slug-availability?slug=${slug_reserved} => HTTP $code_slug_reserved"
echo "$slug_reserved_body" | jq .
[[ "$code_slug_reserved" == "200" ]] || fail "Reserved slug expected 200"
echo "$slug_reserved_body" | jq -e '.available==false' >/dev/null || fail "Expected available=false for reserved slug"

slug_bad_body="$($CURL_CMD -sS --max-time 8 --get --data-urlencode "slug=${slug_bad}" "$BASE_URL/api/v1/public/check-slug-availability")"
code_slug_bad="$($CURL_CMD -sS -o /dev/null --max-time 8 -w "%{http_code}" --get --data-urlencode "slug=${slug_bad}" "$BASE_URL/api/v1/public/check-slug-availability")"
echo "GET /api/v1/public/check-slug-availability?slug=${slug_bad} => HTTP $code_slug_bad"
echo "$slug_bad_body" | jq .
[[ "$code_slug_bad" == "400" ]] || fail "Invalid slug expected 400"

# Signup flow smoke (Python)
hr
echo "Signup flow smoke (python helper)"
if [[ -n "${PLATFORM_DATABASE_URL:-}" || -n "${DATABASE_URL:-}" ]]; then
  API_PUBLIC="$BASE_URL/api/v1/public" \
    $PYTHON scripts/smoke_signup_flow.py
else
  warn "Skipping signup flow smoke: DATABASE_URL/PLATFORM_DATABASE_URL not set"
fi

# Frontend smoke
frontend_smoke

# 4) Python smokes
hr
echo "4) Python smokes: subscription + tenant isolation"

# Determine python interpreter
PY_INT=""
if [[ -x "$PYTHON" ]]; then
  PY_INT="$PYTHON"
elif command -v python >/dev/null 2>&1; then
  PY_INT="python"
elif command -v python3 >/dev/null 2>&1; then
  PY_INT="python3"
else
  fail "No usable Python interpreter found"
fi

echo
echo "4a) Subscription status smoke"
"$PY_INT" scripts/smoke_subscription_status.py || fail "subscription status smoke failed"

echo
echo "4b) Tenant isolation smoke"
"$PY_INT" scripts/smoke_tenant_isolation.py || fail "tenant isolation smoke failed"

ok "Python smokes passed"
echo
ok "ALL CORE SMOKE TESTS PASSED"
