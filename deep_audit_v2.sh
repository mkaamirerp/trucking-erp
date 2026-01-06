#!/usr/bin/env bash
set -euo pipefail

TS="$(date +%Y%m%d_%H%M%S)"
OUT="$HOME/trucking_erp/audit_v2_${TS}.txt"

redact() {
  perl -pe '
    s/\b(PASSWORD|PASS|SECRET|TOKEN|API_KEY|KEY)=\S+/$1=REDACTED/ig;
    s#(postgres(?:ql)?(?:\+asyncpg|\+psycopg2)?://[^:/@]+:)[^@/]+@#$1REDACTED@#ig;
  '
}
say(){ printf "\n\n===== %s =====\n" "$*" | tee -a "$OUT" >/dev/null; }
cmd(){ printf "\n$ %s\n" "$*" | tee -a "$OUT" >/dev/null; bash -lc "$*" 2>&1 | redact | tee -a "$OUT" >/dev/null; }

{
  echo "Trucking ERP Deep Audit v2 (Read-only)"
  echo "Generated: $(date -Is)"
  echo "Host: $(hostname)"
  echo "User: $(whoami)"
  echo "-----------------------------------"
} > "$OUT"

say "1) Host OS + uptime"
cmd "uname -a"
cmd "uptime"
cmd "lsb_release -a 2>/dev/null || cat /etc/os-release || true"

say "2) Ports + owners (full map)"
cmd "ss -ltnp"
cmd "ss -lunp || true"

say "3) Docker inventory"
cmd "docker ps -a --no-trunc"
cmd "docker images"
cmd "docker network ls"
cmd "docker volume ls"

say "4) Nginx truth (configs + enabled sites)"
cmd "nginx -t 2>&1 || true"
cmd "nginx -T 2>/dev/null | head -n 200 || true"
cmd "ls -la /etc/nginx/sites-enabled /etc/nginx/sites-available 2>/dev/null || true"
cmd "grep -RInE 'listen |server_name|proxy_pass|upstream' /etc/nginx/sites-enabled 2>/dev/null | head -n 200 || true"

say "5) Running API process details (host uvicorn)"
cmd "pgrep -a -f 'uvicorn app.main:app' || true"
cmd "ps -p 365700 -o pid,ppid,user,etime,cmd 2>/dev/null || true"
cmd "readlink -f /proc/365700/cwd 2>/dev/null || true"
cmd "tr '\\0' '\\n' < /proc/365700/environ 2>/dev/null | egrep -i 'DATABASE_URL|POSTGRES_ADMIN_URL|ENV|APP_ENV|PORT' || true"
cmd "systemctl list-units --type=service | egrep -i 'uvicorn|trucking|fastapi' || true"

say "6) Repo + docker build context (why web folder missing)"
cmd "cd $HOME/trucking_erp && git rev-parse --abbrev-ref HEAD 2>/dev/null && git rev-parse --short HEAD 2>/dev/null || true"
cmd "cd $HOME/trucking_erp && ls -la"
cmd "cd $HOME/trucking_erp && find . -maxdepth 3 -type f \\( -iname 'dockerfile*' -o -iname 'docker-compose*.yml' -o -iname '*.compose.yml' \\) -print"
cmd "cd $HOME/trucking_erp && grep -RInE 'COPY|ADD|web/|frontend|static' -n . 2>/dev/null | head -n 200"

say "7) Env files on host (inventory only)"
cmd "cd $HOME/trucking_erp && ls -la .env* 2>/dev/null || true"
cmd "cd $HOME/trucking_erp && egrep -n 'DATABASE_URL|POSTGRES_ADMIN_URL|TENANT_DB_APP|DB_' .env 2>/dev/null || true"

say "8) Postgres truth (host packages vs docker)"
cmd "systemctl status postgresql 2>/dev/null || true"
cmd "ps -ef | egrep -i 'postgres|postmaster' | head -n 80"
cmd "docker exec -i shared-postgres sh -lc 'export PAGER=cat; psql -X -P pager=off -U postgres -d postgres -c \"select current_database();\"' 2>/dev/null || true"
cmd "docker exec -i shared-postgres sh -lc 'export PAGER=cat; psql -X -P pager=off -U postgres -d postgres -c \"\\l\"' 2>/dev/null || true"

say "9) Python packages (host venv snapshot)"
cmd "$HOME/trucking_erp/venv/bin/python -V 2>/dev/null || true"
cmd "$HOME/trucking_erp/venv/bin/pip freeze 2>/dev/null | head -n 300 || true"

say "10) Summary"
{
  echo "- Runtime API: host uvicorn (see section 5)"
  echo "- DB: docker shared-postgres on :5432 (see section 8)"
  echo "- Nginx: host (see section 4)"
  echo "- Frontend/web: determine via section 6 COPY/ADD + repo tree"
} >> "$OUT"

echo "Wrote report: $OUT"
