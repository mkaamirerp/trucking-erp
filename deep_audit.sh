#!/usr/bin/env bash
set -euo pipefail

TS="$(date +%Y%m%d_%H%M%S)"
OUT="$HOME/trucking_erp/audit_report_${TS}.txt"

redact() {
  perl -pe '
    s/\b(PASSWORD|PASS|SECRET|TOKEN|API_KEY|KEY)=\S+/$1=REDACTED/ig;
    s#(postgres(?:ql)?(?:\+asyncpg|\+psycopg2)?://[^:/@]+:)[^@/]+@#$1REDACTED@#ig;
  '
}

say() { printf "\n\n===== %s =====\n" "$*" | tee -a "$OUT" >/dev/null; }
cmd() { printf "\n$ %s\n" "$*" | tee -a "$OUT" >/dev/null; bash -lc "$*" 2>&1 | redact | tee -a "$OUT" >/dev/null; }

is_running() {
  local c="$1"
  docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null | grep -qx 'running'
}

{
  echo "Trucking ERP Deep Audit Report"
  echo "Generated: $(date -Is)"
  echo "Host: $(hostname)"
  echo "User: $(whoami)"
  echo "-----------------------------------"
} > "$OUT"

say "1) Docker Container Reality (Truth)"
cmd "docker ps -a --no-trunc"
cmd "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}'"

say "2) Host ports (what is actually listening)"
cmd "ss -ltnp | egrep ':(5432|5434|8000|8001|80|443)\\b' || echo 'No listeners on key ports'"

say "3) Docker network truth (trucking_net)"
cmd "docker network ls | grep -E 'trucking_net|trucking' || true"
cmd "docker network inspect trucking_net --format '{{json .Containers}}' || echo 'No trucking_net or not inspectable'"

say "4) Container inspection (ports/env/volumes) + safe exec when running"
for name in trucking_api trucking_api_8001 shared-postgres trucking_erp_db nginx; do
  if docker inspect "$name" >/dev/null 2>&1; then
    say "Inspecting: $name"
    cmd "docker inspect $name --format \$'NAME={{.Name}}\nIMAGE={{.Config.Image}}\nSTATUS={{.State.Status}}\nPORTS={{json .HostConfig.PortBindings}}\nMOUNTS={{json .Mounts}}\nBINDS={{json .HostConfig.Binds}}'"

    if is_running "$name"; then
      say "Runtime ENV (filtered) inside: $name"
      cmd "docker exec $name sh -lc 'env | egrep -i \"DATABASE|POSTGRES|PORT|ENV\" | sort || true'"

      if [ "$name" = "trucking_api" ] || [ "$name" = "trucking_api_8001" ]; then
        say "Filesystem check inside: $name"
        cmd "docker exec $name sh -lc 'ls -la /app && echo ---- && find /app -maxdepth 2 -type d -print'"
        cmd "docker exec $name sh -lc 'ls -la /app/web 2>/dev/null || echo WEB_FOLDER_MISSING_IN_CONTAINER'"
      fi
    else
      say "Skipping docker exec for $name (not running)"
    fi

    say "Last 80 log lines: $name"
    cmd "docker logs --tail 80 $name || true"
  fi
done

say "5) Host-side leftovers (env files + zombie processes)"
cmd "ls -la $HOME/trucking_erp/.env* 2>/dev/null || echo 'No .env files on host'"
cmd "ps -ef | egrep -i 'uvicorn|gunicorn|nginx|postgres|postmaster' | grep -v egrep || echo 'No matching host processes'"

say "6) Diagnostic Summary"
{
  echo "Audit Complete."
  echo "- If BINDS/MOUNTS are empty -> code is baked into image."
  echo "- If /app/web missing -> frontend not copied into image and not mounted."
  echo "- Port conflicts -> see section 2 ss output."
  echo "- Env truth -> see section 4 runtime ENV (filtered)."
} >> "$OUT"

echo "Wrote report: $OUT"
