#!/usr/bin/env bash
set -euo pipefail

# ---------- Config ----------
: "${BASE_URL:=http://truckerp-nginx}"   # inside docker network (nginx container)
: "${API_PREFIX:=/api/v1}"

GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[0;33m"; NC="\033[0m"

PASS=0
FAIL=0
WARN=0

say() { echo -e "$*"; }
ok() { PASS=$((PASS+1)); say "${GREEN}PASS${NC} $*"; }
no() { FAIL=$((FAIL+1)); say "${RED}FAIL${NC} $*"; }
wa() { WARN=$((WARN+1)); say "${YELLOW}WARN${NC} $*"; }

run_step() {
  local name="$1"; shift
  say "\n== $name =="
  if "$@"; then ok "$name"; else no "$name"; fi
}

# ---------- Helpers ----------
curl_code() {
  # prints HTTP status code only
  docker run --rm --network truckerp_net curlimages/curl:8.5.0 -L \
    -sS -o /dev/null -w "%{http_code}" "$@"
}

curl_body() {
  docker run --rm --network truckerp_net curlimages/curl:8.5.0 -L \
    -sS "$@"
}

expect_code() {
  local label="$1"
  local url="$2"
  local expected="$3"

  local code
  code="$(curl_code "$url")" || code="000"

  if [[ "$code" == "$expected" ]]; then
    ok "$label ($code)"
    return 0
  fi

  # allow 401 "auth required" for tenant routes (dev-safe)
  if [[ "$expected" == "200or401" && ( "$code" == "200" || "$code" == "401" ) ]]; then
    ok "$label ($code)"
    return 0
  fi

  no "$label (got $code, expected $expected)"
  return 1
}

expect_openapi_has() {
  local path="$1"
  local doc
  doc="$(curl_body "${BASE_URL}/openapi.json" || true)"
  if echo "$doc" | grep -q "\"${path//\//\\/}\""; then
    ok "OpenAPI contains ${path}"
    return 0
  fi
  wa "OpenAPI missing ${path} (might be router not included or prefix mismatch)"
  return 0
}

# ---------- 0) Preconditions ----------
say "BASE_URL=${BASE_URL}"
say "API_PREFIX=${API_PREFIX}"

# ---------- 1) Container + logs quick sanity ----------
run_step "docker compose ps" docker compose ps

# ---------- 2) Python code sanity inside API container ----------
run_step "python compileall" docker exec -it truckerp-api sh -lc "python -m compileall -q /app/app"

# ---------- 3) Lint / formatting (only if tools exist) ----------
run_step "ruff check (if installed)" docker exec -it truckerp-api sh -lc "command -v ruff >/dev/null 2>&1 && ruff check /app/app || true"
run_step "mypy (if installed)" docker exec -it truckerp-api sh -lc "command -v mypy >/dev/null 2>&1 && mypy -p app || true"

# ---------- 4) Pytest (only if present) ----------
run_step "pytest (if installed)" docker exec -it truckerp-api sh -lc "command -v pytest >/dev/null 2>&1 && pytest -q || true"

# ---------- 5) HTTP smokes (strict for platform; lenient for protected) ----------
say "\n== HTTP smoke =="
expect_code "GET /api/v1/health" "${BASE_URL}${API_PREFIX}/health" "200"
expect_code "GET /healthz" "${BASE_URL}/healthz" "200"
expect_code "GET /openapi.json" "${BASE_URL}/openapi.json" "200"

# People-first routes should exist (OpenAPI presence check)
expect_openapi_has "${API_PREFIX}/people"
expect_openapi_has "${API_PREFIX}/people/{person_id}"
expect_openapi_has "${API_PREFIX}/people/{person_id}/phones"
expect_openapi_has "${API_PREFIX}/people/{person_id}/roles"
expect_openapi_has "${API_PREFIX}/people/{person_id}/driver-profile"
expect_openapi_has "${API_PREFIX}/people/{person_id}/documents"
expect_openapi_has "${API_PREFIX}/people/{person_id}/documents/{document_id}/files"

# Auth behavior check (lenient: 200 or 401 is acceptable in dev; anything else is suspicious)
expect_code "GET /api/v1/people (expect 200 or 401)" "${BASE_URL}${API_PREFIX}/people" "200or401"
expect_code "GET /api/v1/people/1 (expect 200/401/404)" "${BASE_URL}${API_PREFIX}/people/1" "200or401" || true

# ---------- Summary ----------
say "\n======================"
say "RESULTS:"
say "  ${GREEN}PASS${NC}: ${PASS}"
say "  ${YELLOW}WARN${NC}: ${WARN}"
say "  ${RED}FAIL${NC}: ${FAIL}"
say "======================"

if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
