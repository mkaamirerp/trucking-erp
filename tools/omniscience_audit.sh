#!/usr/bin/env bash
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# TRUCKERP OMNISCIENCE AUDIT ENGINE - COMPLETE VERSION
# ------------------------------------------------------------------------------

# Config
ROOT_DIR="${ROOT_DIR:-/home/admin/trucking_erp}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/runtime/reports}"
TS="$(date +%Y%m%d_%H%M%S)"
REPORT="${REPORT_DIR}/omniscience_audit_${TS}.txt"
TMPDIR="$(mktemp -d)"
AWS_REGION="${AWS_REGION:-us-east-1}"
SSM_PATH_PLATFORM="${SSM_PATH_PLATFORM:-/truckerp/prod/platform/}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
NETWORK="${NETWORK:-truckerp_net}"
API_NAME="${API_NAME:-truckerp-api}"
API_HOST="${API_HOST:-truckerp-api}"
API_PORT="${API_PORT:-8000}"
NGINX_NAME="${NGINX_NAME:-truckerp-nginx}"
POSTGRES_NAME="${POSTGRES_NAME:-truckerp-postgres}"
PLATFORM_DB="${PLATFORM_DB:-trucking_erp}"
TENANT_DB="${TENANT_DB:-truckerp}"
ADMIN_DB="${ADMIN_DB:-postgres}"
TENANT_SLUG="${TENANT_SLUG:-truckerp}"
RENDERED_ENV="/run/secrets/truckerp.env"
VAULT_AGENT_NAME="${VAULT_AGENT_NAME:-truckerp-vault-agent}"

PASS=0
WARN=0
FAIL=0
NOTES=()

# Helper Functions
cleanup() { rm -rf "$TMPDIR" >/dev/null 2>&1 || true; }
trap cleanup EXIT
mkdir -p "$REPORT_DIR"

hr() { echo "============================================================" | tee -a "$REPORT"; }
h2() { echo -e "\n## $*" | tee -a "$REPORT"; }
log() { echo -e "$*" | tee -a "$REPORT"; }

inc_pass() { PASS=$((PASS+1)); }
inc_warn() { WARN=$((WARN+1)); NOTES+=("WARN: $*"); }
inc_fail() { FAIL=$((FAIL+1)); NOTES+=("FAIL: $*"); }

section_result() {
  local ok="$1"; shift; local msg="$*"
  if [[ "$ok" == "PASS" ]]; then log "✅ $msg"; inc_pass
  elif [[ "$ok" == "WARN" ]]; then log "⚠️  $msg"; inc_warn "$msg"
  else log "❌ $msg"; inc_fail "$msg"; fi
}

need_cmd() { 
  if ! command -v "$1" >/dev/null 2>&1; then 
    section_result WARN "Missing: $1"; 
    return 1
  fi
  return 0
}

# Read key from container's environment file
read_env_key() {
    local key="$1"
    docker exec "$API_NAME" grep -E "^${key}=" "$RENDERED_ENV" 2>/dev/null | head -n 1 | cut -d= -f2- || true
}

# URL parsing functions
mask_url() { sed -E 's#(postgresql(\+asyncpg)?://[^:]+:)[^@]+(@)#\1***\3#g'; }
mask_kv() { sed -E 's#^(JWT_SECRET|POSTGRES_PASSWORD)=.*#\1=***#'; }

extract_host_from_url() { 
  echo "$1" | sed -E 's#^postgresql(\+asyncpg)?://[^@]+@([^:/]+).*$#\2#' 2>/dev/null || true
}

extract_db_from_url() { 
  echo "$1" | sed -E 's#^.*/([^/?]+)(\?.*)?$#\1#' 2>/dev/null || true
}

extract_pw_from_url() { 
  echo "$1" | sed -E 's#^postgresql(\+asyncpg)?://[^:]+:([^@]+)@.*$#\2#' 2>/dev/null || true
}

extract_user_from_url() {
  echo "$1" | sed -E 's#^postgresql(\+asyncpg)?://([^:]+):[^@]+@.*$#\2#' 2>/dev/null || true
}

# Test API endpoint (GET)
test_endpoint() {
    local endpoint="$1"
    local expected_code="${2:-200}"
    local timeout="${3:-10}"
    
    local response_code
    response_code=$(docker run --rm --network "$NETWORK" \
        curlimages/curl:latest \
        curl -s -o /dev/null -w "%{http_code}" \
        "http://${API_HOST}:${API_PORT}${endpoint}" \
        --max-time "$timeout" 2>/dev/null || echo "000")
    
    if [[ "$response_code" == "$expected_code" ]]; then
        return 0
    else
        log "  HTTP $response_code (expected $expected_code) for $endpoint"
        return 1
    fi
}

# Test API endpoint with headers (GET). Pass header as "Header-Name: value" in second arg.
test_endpoint_headers() {
    local endpoint="$1"
    local header_value="$2"
    local expected_code="${3:-200}"
    local timeout="${4:-10}"
    local response_code
    response_code=$(docker run --rm --network "$NETWORK" \
        -e "CURL_HEADER=$header_value" \
        curlimages/curl:latest \
        sh -c 'curl -s -o /dev/null -w "%{http_code}\n" -H "$CURL_HEADER" "http://'"${API_HOST}"':'"${API_PORT}"''"${endpoint}"'" --max-time '"$timeout"' 2>/dev/null || echo "000"' | tail -n1)
    if [[ "$response_code" == "$expected_code" ]]; then
        return 0
    else
        log "  HTTP $response_code (expected $expected_code) for $endpoint (with headers)"
        return 1
    fi
}

# Test API endpoint POST (e.g. login). Capture only status code (last line) in case body leaks to stdout.
test_endpoint_post() {
    local endpoint="$1"
    local body="${2:-{}}"
    local extra_headers="${3:-}"
    local expected_code="${4:-200}"
    local timeout="${5:-10}"
    local response_code
    response_code=$(docker run --rm --network "$NETWORK" \
        -e "CURL_BODY=$body" \
        -e "CURL_EXTRA=$extra_headers" \
        curlimages/curl:latest \
        sh -c 'curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" $CURL_EXTRA -d "$CURL_BODY" "http://'"${API_HOST}"':'"${API_PORT}"''"${endpoint}"'" --max-time '"$timeout"' 2>/dev/null || echo "000"' | tail -n1)
    if [[ "$response_code" == "$expected_code" ]]; then
        return 0
    else
        log "  HTTP $response_code (expected $expected_code) for POST $endpoint"
        return 1
    fi
}

# Start Audit
hr
log "TruckERP Omniscience Audit - COMPLETE"
log "Timestamp: $(date -Is)"
hr

h2 "0) Tooling"
need_cmd docker
need_cmd aws || true
need_cmd jq || true
need_cmd curl || true

h2 "1) Containers & Restart Policies"
API_CID="$(docker ps -qf "name=^${API_NAME}$" || true)"
NGINX_CID="$(docker ps -qf "name=^${NGINX_NAME}$" || true)"
PG_CID="$(docker ps -qf "name=^${POSTGRES_NAME}$" || true)"

log "API: ${API_CID:-none} NGINX: ${NGINX_CID:-none} PG: ${PG_CID:-none}"

# Container running checks
if [[ -z "${API_CID:-}" ]]; then
    section_result FAIL "API container not running"
else
    section_result PASS "API container running"
fi

if [[ -z "${NGINX_CID:-}" ]]; then
    section_result WARN "Nginx container not running"
else
    section_result PASS "Nginx container running"
fi

if [[ -z "${PG_CID:-}" ]]; then
    section_result FAIL "PostgreSQL container not running"
else
    section_result PASS "PostgreSQL container running"
fi

# Docker health checks
if docker inspect "$API_NAME" --format='{{.State.Health.Status}}' >/dev/null 2>&1; then
    API_HEALTH="$(docker inspect "$API_NAME" --format='{{.State.Health.Status}}')"
    log "API health status: $API_HEALTH"
    section_result PASS "API has Docker health check"
else
    section_result FAIL "API missing Docker HEALTHCHECK - won't auto-recover"
fi

# Restart policies
API_RESTART="$(docker inspect "$API_NAME" --format='{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null || echo "unknown")"
NGINX_RESTART="$(docker inspect "$NGINX_NAME" --format='{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null || echo "unknown")"
PG_RESTART="$(docker inspect "$POSTGRES_NAME" --format='{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null || echo "unknown")"

[[ "$API_RESTART" == "unless-stopped" ]] && section_result PASS "API restart: unless-stopped" || section_result WARN "API restart: $API_RESTART (should be unless-stopped)"
[[ "$NGINX_RESTART" == "unless-stopped" ]] && section_result PASS "Nginx restart: unless-stopped" || section_result FAIL "Nginx restart: $NGINX_RESTART (should be unless-stopped, NOT always)"
[[ "$PG_RESTART" == "unless-stopped" ]] && section_result PASS "PostgreSQL restart: unless-stopped" || section_result WARN "PostgreSQL restart: $PG_RESTART"

h2 "2) SSM Health & Secrets"
if command -v aws >/dev/null 2>&1; then
  if aws sts get-caller-identity >/dev/null 2>&1; then
    section_result PASS "AWS credentials valid"
    
    # Test SSM access
    if aws ssm get-parameter --name "${SSM_PATH_PLATFORM}DATABASE_URL" --region "$AWS_REGION" --query Parameter.Value --output text >/dev/null 2>&1; then
        section_result PASS "SSM parameter access OK"
        
        # Check for JWT_SECRET in SSM
        if aws ssm get-parameter --name "${SSM_PATH_PLATFORM}JWT_SECRET" --region "$AWS_REGION" --query Parameter.Value --output text >/dev/null 2>&1; then
            section_result PASS "JWT_SECRET exists in SSM"
        else
            section_result FAIL "JWT_SECRET missing from SSM"
        fi
    else
        section_result WARN "Cannot read SSM parameters"
    fi
  else
    section_result FAIL "AWS credentials invalid"
  fi
else
  section_result WARN "aws CLI missing - skipping SSM checks"
fi

h2 "3) Rendered env-file (in container)"
if docker exec "$API_NAME" test -f "$RENDERED_ENV" 2>/dev/null; then
  section_result PASS "Rendered env exists in container"
  
  # Show masked DATABASE_URL
  DBURL_PREVIEW="$(read_env_key "DATABASE_URL")"
  if [[ -n "$DBURL_PREVIEW" ]]; then
    log "DATABASE_URL: $(echo "$DBURL_PREVIEW" | mask_url)"
  else
    section_result WARN "DATABASE_URL not found in env file"
  fi
  
  # Check JWT_SECRET in container
  JWT_SECRET_PREVIEW="$(read_env_key "JWT_SECRET")"
  if [[ -n "$JWT_SECRET_PREVIEW" ]]; then
    section_result PASS "JWT_SECRET loaded in container"
    log "JWT_SECRET length: ${#JWT_SECRET_PREVIEW} chars"
  else
    section_result FAIL "JWT_SECRET not loaded in container"
  fi
else
  section_result FAIL "Rendered env missing from container"
fi

h2 "4) Multi-Database Connectivity"
if [[ -n "${API_CID:-}" ]]; then
  DBURL="$(read_env_key "DATABASE_URL")"
  if [[ -n "$DBURL" ]]; then
    PW="$(extract_pw_from_url "$DBURL")"
    HOST="$(extract_host_from_url "$DBURL")"
    USER="$(extract_user_from_url "$DBURL")"
    USER="${USER:-postgres}"
    
    # Test PLATFORM database
    log "Testing connection to $HOST/$PLATFORM_DB as $USER..."
    if docker run --rm --network "$NETWORK" \
        -e PGPASSWORD="$PW" \
        postgres:16-alpine \
        psql -h "$HOST" -U "$USER" -d "$PLATFORM_DB" -c "select 1;" >/dev/null 2>&1; then
      section_result PASS "Platform DB ($PLATFORM_DB) connectivity OK"
    else
      section_result FAIL "Platform DB ($PLATFORM_DB) connectivity FAILED"
    fi
    
    # Test TENANT database
    log "Testing connection to $HOST/$TENANT_DB as $USER..."
    if docker run --rm --network "$NETWORK" \
        -e PGPASSWORD="$PW" \
        postgres:16-alpine \
        psql -h "$HOST" -U "$USER" -d "$TENANT_DB" -c "select 1;" >/dev/null 2>&1; then
      section_result PASS "Tenant DB ($TENANT_DB) connectivity OK"
    else
      section_result WARN "Tenant DB ($TENANT_DB) connectivity FAILED (may not be created yet)"
    fi
    
    # Test ADMIN database
    log "Testing connection to $HOST/$ADMIN_DB as $USER..."
    if docker run --rm --network "$NETWORK" \
        -e PGPASSWORD="$PW" \
        postgres:16-alpine \
        psql -h "$HOST" -U "$USER" -d "$ADMIN_DB" -c "select 1;" >/dev/null 2>&1; then
      section_result PASS "Admin DB ($ADMIN_DB) connectivity OK"
    else
      section_result FAIL "Admin DB ($ADMIN_DB) connectivity FAILED"
    fi
  else
    section_result FAIL "DATABASE_URL not found"
  fi
else
  section_result WARN "Skipping DB check - API container not running"
fi

h2 "5) Network Verification"
if [[ -n "${API_CID:-}" && -n "${PG_CID:-}" ]]; then
  if docker network inspect "$NETWORK" >/dev/null 2>&1; then
    section_result PASS "Network '$NETWORK' exists"
    
    # Check if both containers are on the same network
    API_NETWORK="$(docker inspect "$API_CID" --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}')"
    PG_NETWORK="$(docker inspect "$PG_CID" --format '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}')"
    
    if [[ "$API_NETWORK" == "$PG_NETWORK" ]]; then
      section_result PASS "API and PostgreSQL on same network"
    else
      section_result WARN "API and PostgreSQL on different networks"
    fi
  else
    section_result FAIL "Network '$NETWORK' does not exist"
  fi
fi

h2 "6) API Health Check"
if [[ -n "${API_CID:-}" ]]; then
  log "Testing API connectivity..."
  
  ENDPOINTS=("/health" "/api/health" "/status" "/api/v1/health" "/healthz")
  HEALTH_OK=false
  HEALTH_ENDPOINT=""
  
  for endpoint in "${ENDPOINTS[@]}"; do
    if test_endpoint "$endpoint" "200" "5"; then
      log "  ✓ Endpoint ${endpoint} responded"
      HEALTH_OK=true
      HEALTH_ENDPOINT="$endpoint"
      break
    else
      log "  ✗ Endpoint ${endpoint} failed"
    fi
  done
  
  if $HEALTH_OK; then
    section_result PASS "API health endpoint accessible (${HEALTH_ENDPOINT})"
  else
    section_result FAIL "API health endpoints not accessible"
  fi
fi

h2 "7) SSL/TLS Verification"
if [[ -n "${NGINX_CID:-}" ]]; then
  # Check if SSL is configured in nginx
  if docker exec "$NGINX_NAME" nginx -T 2>/dev/null | grep -q "ssl_certificate"; then
    section_result PASS "SSL certificates configured in nginx"
    
    # Test HTTPS connection
    if curl -sk --connect-timeout 5 https://localhost/api/v1/health >/dev/null 2>&1; then
      section_result PASS "HTTPS endpoint responding"
    else
      section_result WARN "HTTPS endpoint not responding (may be development)"
    fi
  else
    section_result WARN "No SSL certificates found in nginx config (development mode)"
  fi
fi

h2 "8) Port Security Check"
if [[ -n "${API_CID:-}" ]]; then
  # Check if API is only exposed internally (not to host)
  API_PORTS=$(docker inspect "$API_NAME" --format='{{range $p, $conf := .NetworkSettings.Ports}}{{$p}} {{end}}' 2>/dev/null || true)
  if [[ "$API_PORTS" =~ 8000/tcp ]]; then
    # Check if it's mapped to host
    API_HOST_PORT=$(docker inspect "$API_NAME" --format='{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}' 2>/dev/null || echo "")
    if [[ -n "$API_HOST_PORT" ]]; then
      section_result FAIL "API port 8000 exposed to host on port $API_HOST_PORT - SECURITY RISK"
    else
      section_result PASS "API port 8000 not exposed to host (internal only)"
    fi
  else
    section_result PASS "API not exposing ports externally"
  fi
fi

h2 "9) Memory & Resource Limits"
if [[ -n "${API_CID:-}" ]]; then
  # Check if containers have memory limits (prevents swap death)
  for container in "$API_NAME" "$NGINX_NAME" "$POSTGRES_NAME"; do
    if docker inspect "$container" >/dev/null 2>&1; then
      MEM_LIMIT=$(docker inspect "$container" --format='{{.HostConfig.Memory}}' 2>/dev/null || echo "0")
      if [[ "$MEM_LIMIT" -eq 0 ]]; then
        section_result WARN "$container has no memory limit"
      else
        log "  $container memory limit: $((MEM_LIMIT / 1024 / 1024))MB"
      fi
    fi
  done
fi

h2 "10) Volume Backup Check"
if [[ -n "${PG_CID:-}" ]]; then
  # Check if PostgreSQL data is in a volume (for backups)
  PG_VOLUMES=$(docker inspect "$POSTGRES_NAME" --format='{{range .Mounts}}{{.Destination}} {{end}}' 2>/dev/null || true)
  if [[ "$PG_VOLUMES" =~ /var/lib/postgresql/data ]]; then
    section_result PASS "PostgreSQL data in Docker volume (backup-able)"
  else
    section_result FAIL "PostgreSQL data NOT in volume - DATA LOSS RISK on container removal"
  fi
fi

h2 "11) Tenant Routing Smoke Tests"
if [[ -n "${API_CID:-}" ]]; then
  log "Testing tenant routing endpoints..."
  
  # Test 1: Health endpoint (should work without auth)
  if test_endpoint "/api/v1/health" "200" "10"; then
    section_result PASS "Public health endpoint OK"
  else
    section_result FAIL "Public health endpoint failed"
  fi
  
  # Test 2: Public tenant status by slug (no auth); 200 if tenant exists, 404 if slug not in DB
  if test_endpoint "/api/v1/public/tenant/${TENANT_SLUG}" "200" "10" || \
     test_endpoint "/api/v1/public/tenant/${TENANT_SLUG}" "404" "10"; then
    section_result PASS "Public tenant status endpoint OK (200 or 404)"
  else
    section_result FAIL "Public tenant status /api/v1/public/tenant/${TENANT_SLUG} failed"
  fi
  
  # Test 3: No tenant → 400 on tenant-scoped route
  if test_endpoint "/api/v1/drivers" "400" "10"; then
    section_result PASS "Tenant-scoped route returns 400 without tenant"
  else
    section_result FAIL "GET /api/v1/drivers without tenant (expected 400)"
  fi
  
  # Test 4: Invalid tenant ID → 403
  if test_endpoint_headers "/api/v1/drivers" "X-Tenant-ID: 99999" "403" "10"; then
    section_result PASS "Tenant-scoped route returns 403 for invalid tenant"
  else
    section_result FAIL "GET /api/v1/drivers with invalid tenant (expected 403)"
  fi
  
  # Test 5: Valid tenant but no auth → 403 (membership gate)
  if test_endpoint_headers "/api/v1/drivers" "X-Tenant-ID: 24" "403" "10"; then
    section_result PASS "Tenant-scoped route returns 403 without auth (membership gate)"
  else
    section_result FAIL "GET /api/v1/drivers with tenant, no auth (expected 403)"
  fi
  
  # Test 6: Auth login – GET requires tenant (middleware) → 400; POST without tenant → 400
  if test_endpoint "/api/v1/auth/login" "400" "5"; then
    section_result PASS "GET /api/v1/auth/login returns 400 (tenant required)"
  else
    section_result FAIL "GET /api/v1/auth/login (expected 400)"
  fi
  if test_endpoint_post "/api/v1/auth/login" "{}" "" "400" "5"; then
    section_result PASS "POST /api/v1/auth/login (no tenant) returns 400"
  else
    section_result FAIL "POST /api/v1/auth/login without tenant (expected 400)"
  fi
fi

h2 "12) Nginx Configuration & External Access"
if [[ -n "${NGINX_CID:-}" ]]; then
  if docker exec "$NGINX_NAME" nginx -t >/dev/null 2>&1; then
    section_result PASS "Nginx configuration is valid"
  else
    section_result FAIL "Nginx configuration has errors"
  fi
  
  # Test nginx from outside
  log "Testing nginx externally..."
  if curl -s -f --max-time 5 "http://localhost/health" >/dev/null 2>&1 || \
     curl -s -f --max-time 5 "http://localhost/api/v1/health" >/dev/null 2>&1; then
    section_result PASS "Nginx routing to API"
  else
    section_result WARN "Nginx not routing to API (or API not responding)"
  fi
fi

h2 "13) Docker Compose Validation"
if [[ -f "$COMPOSE_FILE" ]]; then
  section_result PASS "Docker compose file exists"
  log "  Compose file: $COMPOSE_FILE"
  
  # Validate compose syntax
  if command -v docker-compose >/dev/null 2>&1; then
    if docker-compose -f "$COMPOSE_FILE" config >/dev/null 2>&1; then
      section_result PASS "Docker compose syntax valid"
    else
      section_result FAIL "Docker compose syntax invalid"
    fi
  fi
else
  section_result WARN "Docker compose file not found"
fi

h2 "14) Final Summary"
hr
log "PASS: $PASS | WARN: $WARN | FAIL: $FAIL"
hr

# Critical failure check
CRITICAL_FAILS=0
[[ "$NGINX_RESTART" == "always" ]] && CRITICAL_FAILS=$((CRITICAL_FAILS+1))
docker inspect "$API_NAME" --format='{{.State.Health.Status}}' >/dev/null 2>&1 || CRITICAL_FAILS=$((CRITICAL_FAILS+1))

if [[ ${#NOTES[@]} -gt 0 ]]; then
    log "NOTES:"
    for note in "${NOTES[@]}"; do 
        log " - $note"
    done
fi

log "Report saved to: $REPORT"

if (( CRITICAL_FAILS > 0 )); then
    log "🚨 CRITICAL: $CRITICAL_FAILS issues require immediate attention"
    exit 2
elif (( FAIL > 0 )); then 
    log "OVERALL: ❌ FAIL"
    exit 2
elif (( WARN > 0 )); then 
    log "OVERALL: ⚠️  WARN"
    exit 1
else 
    log "OVERALL: ✅ PASS"
    exit 0
fi
