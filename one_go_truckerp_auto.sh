#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="truckerp.service"
ENV_DIR="/etc/truckerp"
ENV_FILE="${ENV_DIR}/truckerp.env"
OVERRIDE_DIR="/etc/systemd/system/${SERVICE}.d"
OVERRIDE_FILE="${OVERRIDE_DIR}/override.conf"

TENANT_ID="${TENANT_ID:-2}"
POSTGRES_PASS="${POSTGRES_PASS:-test_password_123}"
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
PROVISION_URL="http://127.0.0.1:8000/api/v1/platform/tenants/${TENANT_ID}/provision"

POSTGRES_ADMIN_URL="postgresql+psycopg2://postgres:${POSTGRES_PASS}@${PG_HOST}:${PG_PORT}/postgres"
DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASS}@${PG_HOST}:${PG_PORT}/postgres"

log(){ printf "\n==> %s\n" "$*"; }

need_root(){
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "ERROR: run with sudo"
    exit 1
  fi
}

unit_exists(){
  systemctl list-unit-files | awk '{print $1}' | grep -qx "${SERVICE}"
}

write_kv(){
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|g" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

pid_8000(){
  ss -ltnp 2>/dev/null | awk '/:8000/ {match($0,/pid=([0-9]+)/,a); if(a[1]!=""){print a[1]; exit}}' || true
}

show_env(){
  local pid="$1"
  [[ -z "$pid" ]] && { echo "No PID found on port 8000."; return 0; }
  echo "PID=$pid"
  tr "\0" "\n" < "/proc/${pid}/environ" | egrep 'POSTGRES_ADMIN_URL|DATABASE_URL' || true
}

main(){
  need_root

  log "Check systemd unit: ${SERVICE}"
  unit_exists || { echo "ERROR: ${SERVICE} not found"; exit 1; }

  log "Write EnvironmentFile ${ENV_FILE}"
  mkdir -p "$ENV_DIR"
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  write_kv "POSTGRES_ADMIN_URL" "$POSTGRES_ADMIN_URL"
  write_kv "DATABASE_URL" "$DATABASE_URL"

  log "Wire systemd override to load EnvironmentFile"
  mkdir -p "$OVERRIDE_DIR"
  cat > "$OVERRIDE_FILE" <<EOF
[Service]
EnvironmentFile=${ENV_FILE}
EOF

  log "Reload systemd + restart ${SERVICE}"
  systemctl daemon-reload
  systemctl restart "$SERVICE"

  log "Verify listener on :8000"
  ss -ltnp | awk '/:8000/ {print}' || true

  log "Verify env is loaded into the running process"
  PID="$(pid_8000)"
  show_env "$PID"

  log "Provision tenant ${TENANT_ID}"
  set +e
  RESP="$(curl -sS -i -X POST "$PROVISION_URL")"
  RC=$?
  set -e
  echo "$RESP"

  if [[ $RC -ne 0 ]] || echo "$RESP" | grep -q "500 Internal Server Error"; then
    log "Provisioning still failing — last 120 lines of logs"
    journalctl -u "$SERVICE" -n 120 --no-pager || true
    exit 1
  fi

  log "DONE"
}

main "$@"
