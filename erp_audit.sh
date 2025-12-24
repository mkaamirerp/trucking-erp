#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Trucking ERP - Deep Audit Script (Very Detailed)
# - Scans all git-tracked files
# - Validates Python env, imports, compileall
# - Validates FastAPI app imports and router registration
# - Validates Docker and Postgres container, roles, DB, connectivity
# - Validates Alembic config, env.py, versions, current/head status
# - Starts uvicorn temporarily (background inside script), tests endpoints,
#   captures logs, shuts it down cleanly
# ============================================================

# ---------- Config ----------
PROJECT_DIR="${PROJECT_DIR:-$HOME/trucking_erp}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"

# Use a random port to avoid conflicts
TEST_PORT="${TEST_PORT:-18001}"
TEST_HOST="${TEST_HOST:-127.0.0.1}"
BASE_URL="http://${TEST_HOST}:${TEST_PORT}"

# Known API paths for our phase
HEALTH_PATH="${HEALTH_PATH:-/api/v1/health}"
DRIVERS_PATH="${DRIVERS_PATH:-/api/v1/drivers}"
ROOT_PATH="${ROOT_PATH:-/}"

# If your container name is different, export POSTGRES_CONTAINER
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-trucking_erp_db}"

# ---------- Pretty output ----------
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
NC=$'\033[0m'

hr(){ echo "------------------------------------------------------------------"; }
section(){ hr; echo "SECTION: $1"; hr; }

pass(){ echo -e "${GREEN}PASS${NC} - $*"; }
fail(){ echo -e "${RED}FAIL${NC} - $*"; }
warn(){ echo -e "${YELLOW}WARN${NC} - $*"; }
info(){ echo "INFO - $*"; }

# Collect failures for final summary
FAIL_COUNT=0
FAIL_LIST=()

record_fail(){
  FAIL_COUNT=$((FAIL_COUNT+1))
  FAIL_LIST+=("$1")
}

# ---------- Cleanup ----------
UVICORN_PID=""
TMPDIR="$(mktemp -d)"
LOGFILE="$TMPDIR/uvicorn.log"

cleanup() {
  if [[ -n "${UVICORN_PID}" ]]; then
    if kill -0 "$UVICORN_PID" >/dev/null 2>&1; then
      info "Stopping uvicorn PID=$UVICORN_PID"
      kill "$UVICORN_PID" >/dev/null 2>&1 || true
      sleep 0.7
      kill -9 "$UVICORN_PID" >/dev/null 2>&1 || true
    fi
  fi
  rm -rf "$TMPDIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ---------- Command checks ----------
need_cmd(){
  local c="$1"
  if command -v "$c" >/dev/null 2>&1; then
    pass "Command exists: $c ($(command -v "$c"))"
  else
    fail "Missing command: $c"
    record_fail "Missing command: $c"
  fi
}

# ---------- Start ----------
echo
echo "TRUCKING ERP - DEEP AUDIT REPORT"
echo "Project: $PROJECT_DIR"
echo "Temp:    $TMPDIR"
echo "Test API: $BASE_URL"
echo

# ============================================================
section "0) Preconditions"
# ============================================================

if [[ -d "$PROJECT_DIR" ]]; then
  pass "Project directory exists: $PROJECT_DIR"
else
  fail "Project directory missing: $PROJECT_DIR"
  record_fail "Project directory missing"
  exit 1
fi

cd "$PROJECT_DIR"

need_cmd bash
need_cmd grep
need_cmd sed
need_cmd awk
need_cmd find
need_cmd curl
need_cmd git
need_cmd python3

# Docker optional but expected for our setup
if command -v docker >/dev/null 2>&1; then
  pass "docker installed: $(docker --version 2>&1)"
else
  warn "docker not found (DB checks will be limited)"
fi

# ============================================================
section "1) Git + file inventory (checks EVERY tracked file)"
# ============================================================

if [[ -d .git ]]; then
  pass "Git repository detected"
else
  warn "No .git directory found (file-by-file checks will be limited to filesystem)"
fi

TRACKED_COUNT=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  TRACKED_COUNT="$(git ls-files | wc -l | tr -d ' ')"
  pass "Git tracked files count: $TRACKED_COUNT"

  info "Scanning every tracked file for basic health: (exists, non-empty where expected, bad endings)"
  BAD_MISSING=0
  BAD_CRLF=0
  BAD_TRAIL=0

  while IFS= read -r f; do
    if [[ ! -e "$f" ]]; then
      ((BAD_MISSING+=1))
      echo "  MISSING FILE: $f"
      continue
    fi

    # CRLF check (common issues when editing on Windows)
    if file "$f" 2>/dev/null | grep -q "CRLF"; then
      ((BAD_CRLF+=1))
      echo "  CRLF LINE ENDINGS: $f"
    fi

    # trailing whitespace check (light)
    if grep -n $'[ \t]\r\?$' "$f" >/dev/null 2>&1; then
      ((BAD_TRAIL+=1))
      echo "  TRAILING WHITESPACE DETECTED: $f"
    fi
  done < <(git ls-files)

  if [[ "$BAD_MISSING" -eq 0 ]]; then
    pass "All tracked files exist on disk"
  else
    fail "Missing tracked files: $BAD_MISSING"
    record_fail "Missing tracked files: $BAD_MISSING"
  fi

  if [[ "$BAD_CRLF" -eq 0 ]]; then
    pass "No CRLF issues detected in tracked files"
  else
    warn "CRLF issues found in $BAD_CRLF file(s) (can break scripts on Linux)"
  fi

  if [[ "$BAD_TRAIL" -eq 0 ]]; then
    pass "No obvious trailing whitespace issues detected"
  else
    warn "Trailing whitespace found in $BAD_TRAIL file(s) (not fatal)"
  fi
else
  warn "Not a git work tree; skipping tracked-file scan"
fi

# ============================================================
section "2) Python venv integrity + package checks"
# ============================================================

if [[ -d "$VENV_DIR" ]]; then
  pass "venv directory exists: $VENV_DIR"
else
  fail "venv directory missing: $VENV_DIR"
  record_fail "venv missing"
fi

PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
ALEMBIC="$VENV_DIR/bin/alembic"
UVICORN="$VENV_DIR/bin/uvicorn"

if [[ -x "$PY" ]]; then
  pass "venv python present: $($PY -V 2>&1)"
else
  fail "venv python missing/not executable: $PY"
  record_fail "venv python missing"
fi

if [[ -x "$PIP" ]]; then
  pass "venv pip present: $($PIP -V 2>&1)"
else
  fail "venv pip missing/not executable: $PIP"
  record_fail "venv pip missing"
fi

# Check key Python deps by import, not by pip name
if [[ -x "$PY" ]]; then
  info "Checking required imports (fastapi, uvicorn, sqlalchemy, alembic, pydantic)..."
  set +e
  IMPORT_OUT="$($PY - <<'PY'
import importlib, sys
mods = ["fastapi","uvicorn","sqlalchemy","alembic","pydantic"]
failed=[]
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        failed.append((m, str(e)))
if failed:
    print("IMPORT_FAIL")
    for m,e in failed:
        print(f"{m}: {e}")
    sys.exit(2)
print("IMPORT_OK")
PY
  )"
  CODE=$?
  set -e

  if [[ $CODE -eq 0 ]] && echo "$IMPORT_OUT" | grep -q "IMPORT_OK"; then
    pass "Core imports OK"
  else
    fail "Core imports FAILED"
    record_fail "Core imports failed"
    echo "$IMPORT_OUT" | sed 's/^/  /'
  fi
fi

# ============================================================
section "3) Python code quality checks (compile ALL python files)"
# ============================================================

if [[ -x "$PY" ]]; then
  # Compile everything under app/ (syntax errors show here)
  if [[ -d app ]]; then
    info "Running compileall on app/ (catches syntax errors across files)..."
    set +e
    $PY -m compileall -q app >/dev/null 2>&1
    CODE=$?
    set -e
    if [[ $CODE -eq 0 ]]; then
      pass "compileall OK (no syntax errors in app/)"
    else
      fail "compileall FAILED (syntax error somewhere in app/)"
      record_fail "compileall failed"
      info "Re-run with details:"
      echo "  $PY -m compileall app"
    fi
  else
    fail "app/ directory missing"
    record_fail "app dir missing"
  fi
fi

# ============================================================
section "4) FastAPI app wiring checks (routers registered)"
# ============================================================

# Check file existence
[[ -f app/main.py ]] && pass "Found app/main.py" || { fail "Missing app/main.py"; record_fail "main.py missing"; }

# Parse router include lines
if [[ -f app/main.py ]]; then
  if grep -Eq 'include_router\(.+drivers' app/main.py; then
    pass "main.py includes drivers router registration"
  else
    fail "main.py does NOT include drivers router registration"
    record_fail "drivers router not registered"
  fi

  if grep -Eq 'include_router\(.+health' app/main.py; then
    pass "main.py includes health router registration"
  else
    fail "main.py does NOT include health router registration"
    record_fail "health router not registered"
  fi
fi

# Import the FastAPI app object and print routes
if [[ -x "$PY" ]]; then
  info "Importing app.main:app and printing registered routes..."
  set +e
  ROUTE_OUT="$($PY - <<'PY'
from app.main import app
paths = sorted([(r.path, ",".join(sorted(getattr(r, "methods", []) or []))) for r in app.routes])
print("ROUTES_BEGIN")
for p,m in paths:
    print(f"{p} [{m}]")
print("ROUTES_END")
PY
  2>&1)"
  CODE=$?
  set -e

  if [[ $CODE -eq 0 ]] && echo "$ROUTE_OUT" | grep -q "ROUTES_BEGIN"; then
    pass "FastAPI app import OK; routes listed below"
    echo "$ROUTE_OUT" | sed 's/^/  /'
  else
    fail "FastAPI app import FAILED"
    record_fail "FastAPI app import failed"
    echo "$ROUTE_OUT" | sed 's/^/  /'
  fi
fi

# ============================================================
section "5) Docker + Postgres deep checks (container, db, roles, tables)"
# ============================================================

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    pass "Docker daemon reachable"
  else
    fail "Docker daemon NOT reachable"
    record_fail "docker daemon unreachable"
  fi

  # Check container running
  if docker ps --format '{{.Names}}' | grep -qx "$POSTGRES_CONTAINER"; then
    pass "Postgres container running: $POSTGRES_CONTAINER"
  else
    warn "Postgres container not running (name expected: $POSTGRES_CONTAINER)"
    warn "Running containers:"
    docker ps --format '  - {{.Names}} ({{.Image}})' || true
  fi

  # Detect host port mapping
  HOST_PORT="$(docker inspect -f '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' "$POSTGRES_CONTAINER" 2>/dev/null || true)"
  if [[ -n "$HOST_PORT" ]]; then
    pass "Postgres port mapping: host:$HOST_PORT -> container:5432"
  else
    warn "Could not detect host port mapping for $POSTGRES_CONTAINER (maybe no mapping / different port)"
  fi

  # Inside-container DB checks (doesn't require psql on host)
  if docker ps --format '{{.Names}}' | grep -qx "$POSTGRES_CONTAINER"; then
    info "Running inside-container PostgreSQL checks..."

    # roles
    set +e
    ROLE_OUT="$(docker exec -i "$POSTGRES_CONTAINER" psql -U erp_user -d trucking_erp -c "\du" 2>&1)"
    CODE=$?
    set -e
    if [[ $CODE -eq 0 ]]; then
      pass "Connected inside container as erp_user to trucking_erp; roles list OK"
      echo "$ROLE_OUT" | sed 's/^/  /'
    else
      fail "Could not connect inside container using: psql -U erp_user -d trucking_erp"
      record_fail "DB connect inside container failed"
      echo "$ROLE_OUT" | sed 's/^/  /'
      echo "  Tip: confirm DB name/user match your docker init settings."
    fi

    # list tables
    set +e
    TBL_OUT="$(docker exec -i "$POSTGRES_CONTAINER" psql -U erp_user -d trucking_erp -c "\dt" 2>&1)"
    CODE=$?
    set -e
    if [[ $CODE -eq 0 ]]; then
      pass "Table listing succeeded"
      echo "$TBL_OUT" | sed 's/^/  /'
    else
      warn "Table listing failed (maybe no tables yet / privileges)"
      echo "$TBL_OUT" | sed 's/^/  /'
    fi

    # alembic version table check
    set +e
    AV_OUT="$(docker exec -i "$POSTGRES_CONTAINER" psql -U erp_user -d trucking_erp -c "SELECT to_regclass('public.alembic_version') AS alembic_version_table;" 2>&1)"
    CODE=$?
    set -e
    if [[ $CODE -eq 0 ]]; then
      pass "Checked for alembic_version table"
      echo "$AV_OUT" | sed 's/^/  /'
    else
      warn "Could not check alembic_version table"
      echo "$AV_OUT" | sed 's/^/  /'
    fi
  fi
else
  warn "Skipping Docker/Postgres checks (docker not installed)"
fi

# ============================================================
section "6) Alembic deep checks (config, env.py, versions, head/current)"
# ============================================================

if [[ -x "$ALEMBIC" ]]; then
  pass "Alembic executable exists in venv"
else
  fail "Alembic missing: $ALEMBIC"
  record_fail "alembic missing"
fi

[[ -f alembic.ini ]] && pass "Found alembic.ini" || warn "Missing alembic.ini"
[[ -f alembic/env.py ]] && pass "Found alembic/env.py" || warn "Missing alembic/env.py"
[[ -d alembic/versions ]] && pass "Found alembic/versions" || warn "Missing alembic/versions"

if [[ -x "$ALEMBIC" ]] && [[ -f alembic.ini ]]; then
  info "alembic heads:"
  set +e
  HEADS="$($ALEMBIC heads 2>&1)"
  CODE=$?
  set -e
  if [[ $CODE -eq 0 ]]; then
    pass "alembic heads OK"
    echo "$HEADS" | sed 's/^/  /'
  else
    warn "alembic heads failed (likely DB url/config issue)"
    echo "$HEADS" | sed 's/^/  /'
  fi

  info "alembic current:"
  set +e
  CUR="$($ALEMBIC current 2>&1)"
  CODE=$?
  set -e
  if [[ $CODE -eq 0 ]]; then
    pass "alembic current OK"
    echo "$CUR" | sed 's/^/  /'
  else
    warn "alembic current failed (often DB URL issue)"
    echo "$CUR" | sed 's/^/  /'
  fi
fi

# ============================================================
section "7) Runtime API test (start uvicorn inside script, test endpoints, stop)"
# ============================================================

if [[ -x "$UVICORN" ]]; then
  pass "uvicorn exists in venv"
else
  fail "uvicorn missing: $UVICORN"
  record_fail "uvicorn missing"
fi

# start uvicorn in background (inside script) and test with curl
if [[ -x "$UVICORN" ]]; then
  info "Starting uvicorn on ${TEST_HOST}:${TEST_PORT} (temporary) ..."
  set +e
  "$UVICORN" app.main:app --host "$TEST_HOST" --port "$TEST_PORT" >"$LOGFILE" 2>&1 &
  UVICORN_PID=$!
  set -e

  sleep 1.2

  # Wait up to 5 seconds for it to respond
  READY=0
  for i in {1..10}; do
    if curl -s --max-time 1 "${BASE_URL}/" >/dev/null 2>&1; then
      READY=1
      break
    fi
    sleep 0.5
  done

  if [[ "$READY" -eq 1 ]]; then
    pass "uvicorn is responding"
  else
    fail "uvicorn did not respond on time"
    record_fail "uvicorn not responding"
    info "Last 80 lines of uvicorn log:"
    tail -n 80 "$LOGFILE" | sed 's/^/  /'
  fi

  # endpoint checker with HTTP status codes
  check_http(){
    local path="$1"
    local expect_desc="$2"
    local url="${BASE_URL}${path}"

    local http body
    http="$(curl -sS -m 3 -o "$TMPDIR/resp.json" -w "%{http_code}" "$url" || true)"
    body="$(cat "$TMPDIR/resp.json" 2>/dev/null || true)"

    echo "  Endpoint: $url"
    echo "  Expected: $expect_desc"
    echo "  HTTP:     $http"
    echo "  Body:     $body"

    if [[ "$http" =~ ^2 ]]; then
      pass "Endpoint OK: $path (HTTP $http)"
    else
      fail "Endpoint FAILED: $path (HTTP $http)"
      record_fail "endpoint failed: $path"
      info "Uvicorn log tail (80 lines):"
      tail -n 80 "$LOGFILE" | sed 's/^/  /'
    fi
  }

  hr
  echo "ENDPOINT TESTS (detailed):"
  hr
  check_http "$ROOT_PATH"   'Root should return {"status":"ok"}'
  check_http "$HEALTH_PATH" 'Health should return healthy JSON'
  check_http "$DRIVERS_PATH" 'Drivers should NOT be 404; should return [] or list'

  # Show routes live (OpenAPI)
  hr
  echo "OPENAPI CHECK:"
  hr
  http="$(curl -sS -m 3 -o "$TMPDIR/openapi.json" -w "%{http_code}" "${BASE_URL}/openapi.json" || true)"
  if [[ "$http" == "200" ]]; then
    pass "OpenAPI served (HTTP 200)"
    # show key paths existence
    if grep -q "\"${HEALTH_PATH}\"" "$TMPDIR/openapi.json"; then
      pass "OpenAPI includes $HEALTH_PATH"
    else
      warn "OpenAPI does not show $HEALTH_PATH (maybe router prefix differs)"
    fi
    if grep -q "\"${DRIVERS_PATH}\"" "$TMPDIR/openapi.json"; then
      pass "OpenAPI includes $DRIVERS_PATH"
    else
      warn "OpenAPI does not show $DRIVERS_PATH (maybe router prefix differs)"
    fi
  else
    warn "OpenAPI not available (HTTP $http)"
    tail -n 80 "$LOGFILE" | sed 's/^/  /'
  fi

  # Stop uvicorn now
  info "Stopping uvicorn after tests..."
  kill "$UVICORN_PID" >/dev/null 2>&1 || true
  sleep 0.7
  UVICORN_PID=""
fi

# ============================================================
section "8) Final Summary (everything that failed)"
# ============================================================

if [[ "$FAIL_COUNT" -eq 0 ]]; then
  pass "ALL CHECKS PASSED ✅"
else
  fail "TOTAL FAILURES: $FAIL_COUNT"
  echo "Failures list:"
  for x in "${FAIL_LIST[@]}"; do
    echo "  - $x"
  done
  echo
  echo "Next move: Paste this entire report here and I will fix them in order (Phase 9.1 -> 9.2)."
fi

echo
echo "Audit finished."
echo
