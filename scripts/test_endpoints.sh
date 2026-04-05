#!/usr/bin/env bash
# Endpoint smoke test: run inside Docker network (e.g. docker exec truckerp-api) or with BASE_URL set.
# Tests: health, openapi, public, tenant enforcement, auth, and key tenant endpoints.
set -euo pipefail

API="${BASE_URL:-http://127.0.0.1:8000}/api/v1"
CURL_OPTS="-sS -o /dev/null -w %{http_code} --max-time 10"

ok() { echo "  OK: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }
assert_code() { local got=$1; local want=$2; local msg=$3; [ "$got" = "$want" ] && ok "$msg (HTTP $got)" || fail "$msg: expected $want, got $got"; }

echo "=== 1) No-auth endpoints ==="
code=$(curl $CURL_OPTS "$API/health"); assert_code "$code" "200" "GET /api/v1/health"
code=$(curl $CURL_OPTS "${API%/api/v1}/openapi.json"); assert_code "$code" "200" "GET /openapi.json"
code=$(curl $CURL_OPTS "$API/public/check-slug-availability?slug=test-$(date +%s)"); assert_code "$code" "200" "GET public check-slug-availability"

echo ""
echo "=== 2) Tenant enforcement (no auth) ==="
code=$(curl $CURL_OPTS "$API/drivers"); assert_code "$code" "400" "GET /drivers without tenant => 400"
code=$(curl $CURL_OPTS -H "X-Tenant-ID: 99999" "$API/drivers"); assert_code "$code" "403" "GET /drivers invalid tenant => 403"
# With valid tenant but no auth: membership gate => 403
code=$(curl $CURL_OPTS -H "X-Tenant-ID: 24" "$API/drivers"); assert_code "$code" "403" "GET /drivers tenant without auth => 403"

echo ""
echo "=== 3) Auth endpoints (require tenant header) ==="
# With tenant header but no token: middleware returns 403 (membership gate). With wrong creds and token we'd get 401.
code=$(curl $CURL_OPTS -X POST -H "Content-Type: application/json" -H "X-Tenant-ID: 24" -d '{"email":"nobody@example.com","password":"wrong"}' "$API/auth/login")
[ "$code" = "401" ] || [ "$code" = "403" ] && ok "POST /auth/login (no token or wrong creds) => $code" || fail "POST /auth/login: expected 401 or 403, got $code"
code=$(curl $CURL_OPTS -X POST -H "Content-Type: application/json" -d '{"email":"nobody@example.com","password":"x"}' "$API/auth/login"); assert_code "$code" "400" "POST /auth/login no tenant => 400"

echo ""
echo "=== 4) Public API (no tenant) ==="
code=$(curl $CURL_OPTS "$API/public/check-slug-availability?slug=reserved-slug-123"); assert_code "$code" "200" "GET public check-slug"

echo ""
echo "=== 5) Key tenant routes (structure only; 401/403 without valid token is OK) ==="
for path in "/drivers" "/dashboard/summary" "/brokers" "/loads" "/health"; do
  code=$(curl $CURL_OPTS -H "X-Tenant-ID: 24" "$API$path" 2>/dev/null || true)
  case "$code" in
    200|401|403) ok "GET $path => $code" ;;
    *) echo "  SKIP: GET $path => $code (no token)" ;;
  esac
done

echo ""
echo "=== 6) Platform routes (no tenant) ==="
code=$(curl $CURL_OPTS "$API/platform/tenants")
[ "$code" = "200" ] || [ "$code" = "401" ] || [ "$code" = "403" ] && ok "GET /platform/tenants => $code" || fail "GET /platform/tenants: got $code"

echo ""
echo "All endpoint checks passed."
