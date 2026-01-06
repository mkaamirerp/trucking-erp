#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="truckerp.service"
ENV_DIR="/etc/truckerp"
ENV_FILE="${ENV_DIR}/truckerp.env"
OVERRIDE_DIR="/etc/systemd/system/${SERVICE}.d"
OVERRIDE_FILE="${OVERRIDE_DIR}/override.conf"

POSTGRES_ADMIN_URL="${POSTGRES_ADMIN_URL:-}"
DATABASE_URL="${DATABASE_URL:-}"          # optional
TENANT_ID="${TENANT_ID:-2}"
PROVISION_URL="http://127.0.0.1:8000/api/v1/platform/tenants/${TENANT_ID}/provision"

log() { printf "\n==> %s\n" "$*"; }

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "ERROR: run with sudo"
    exit 1
  fi
}

write_kv() {
  local key="$1" value="$2"
  [[ -z "$value" ]] && return 0
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|g" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

get_pid_8000() {
  ss -ltnp 2>/dev/null | awk '/:8000/ {match($0,/pid=([0-9]+)/,a); if(a[1]!=""){print a[1]; exit}}' || true
}

show_env_from_pid() {
  local pid="$1"
  [[ -z "$pid" ]] && { echo "No PID on 8000"; return 0; }
  echo "PID=$pid"
  tr "\0" "\n" < "/proc/${pid}/environ" | egrep "POSTGRES_ADMIN_URL|DATABASE_URL|TENANT_DB_APP_USER|TENANT_DB_APP_PASSWORD" || true
}

main() {
  need_root

  log "Pre-check: systemd unit exists"
  systemctl list-unit-files | awk '{print $1}' | grep -qx "$SERVICE" || {
    echo "ERROR: $SERVICE not found"
    exit 1
  }

  log "Ensure required env provided"
  if [[ -z "$POSTGRES_ADMIN_URL" && -z "$DATABASE_URL" ]]; then
    echo "ERROR: Provide POSTGRES_ADMIN_URL (preferred) or DATABASE_URL (fallback)."
    echo "Example:"
    echo "  sudo POSTGRES_ADMIN_URL='postgresql+psycopg2://postgres:PASS@127.0.0.1:5432/postgres' TENANT_ID=2 bash $0"
    exit 1
  fi

  log "Write EnvironmentFile: $ENV_FILE"
  mkdir -p "$ENV_DIR"
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  write_kv "POSTGRES_ADMIN_URL" "$POSTGRES_ADMIN_URL"
  write_kv "DATABASE_URL" "$DATABASE_URL"

  log "Wire systemd override to load EnvironmentFile"
  mkdir -p "$OVERRIDE_DIR"
  cat > "$OVERRIDE_FILE" <<EOF
[Service]
EnvironmentFile=$ENV_FILE
EOF

  log "Reload systemd + restart service (single restart)"
  systemctl daemon-reload
  systemctl restart "$SERVICE"

  log "Show lightweight status"
  systemctl --no-pager --full --lines=20 status "$SERVICE" || true

  log "Check port 8000"
  ss -ltnp | awk '/:8000/ {print}' || true
  PID="$(get_pid_8000)"
  log "Check env in running PID (should show POSTGRES_ADMIN_URL or DATABASE_URL)"
  show_env_from_pid "$PID"

  log "Provision tenant $TENANT_ID"
  set +e
  curl -sS -i -X POST "$PROVISION_URL"
  echo
  set -e

  log "Last 120 lines of logs"
  journalctl -u "$SERVICE" -n 120 --no-pager || true

  log "Done"
}

main "$@"
