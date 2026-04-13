#!/usr/bin/env bash
# =============================================================================
# HOST SNAPSHOT TOOL — NOT THE CANONICAL DOCKER + SSM RUNBOOK
# =============================================================================
# This script collects read-only host + Docker state to a temp file. It is
# useful for ad hoc triage on a machine that looks like THIS repo layout, but:
#   - Production operations are defined by docker compose + SSM (see
#     scripts/reload_api.sh, scripts/start_api_with_ssm.sh, docs).
#   - Paths are hardcoded (e.g. /home/admin/trucking_erp) — wrong on other hosts.
#   - Some steps use sudo (ss) — may fail or prompt depending on user/sudoers.
#   - systemd / host nginx sections reflect “what might exist on a host”, not
#     the single source of truth for the compose-based API container.
#
# For canonical recovery and deploy steps, follow repo runbooks — not this dump.
# =============================================================================

set -euo pipefail

ts="$(date -u +%Y%m%d_%H%M%S)"
out="/tmp/house_audit_${ts}.txt"

run() {
  echo >>"$out"
  echo "===== $* =====" >>"$out"
  bash -lc "$*" >>"$out" 2>&1 || true
}

echo "Trucking ERP House Audit (read-only)" >"$out"
echo "Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >>"$out"
echo "Host: $(hostname)" >>"$out"
echo "User: $(whoami)" >>"$out"

run 'uname -a'
run 'uptime'
run 'id'

# --- Host: ports + listeners ---
run 'echo "== LISTENERS (ss -lntup) =="; sudo ss -lntup | sed -n "1,220p"'
run 'echo "== Anything on 80/443/8000/5432 =="; sudo ss -lntup | egrep ":(80|443|8000|5432)\b" || true'

# --- Host: processes that look like API/web ---
run 'echo "== API-ish processes =="; ps auxww | egrep -i "uvicorn|gunicorn|fastapi|starlette|truckerp|nginx|caddy|traefik" | egrep -v "egrep|house_audit" || true'

# --- Host: systemd services (common culprits) ---
run 'echo "== systemd units matching web/api =="; systemctl list-unit-files --type=service | egrep -i "truckerp|uvicorn|gunicorn|fastapi|nginx|caddy|traefik" || true'
run 'echo "== running services matching web/api =="; systemctl --no-pager --type=service --state=running | egrep -i "truckerp|uvicorn|gunicorn|fastapi|nginx|caddy|traefik" || true'
run 'echo "== details for truckerp.service if present =="; systemctl show -p FragmentPath -p UnitFileState -p LoadState -p CanStart -p RefuseManualStart -p RefuseManualStop truckerp.service 2>/dev/null || true'

# --- Docker: containers + port bindings ---
run 'echo "== docker ps =="; docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
run 'echo "== docker ps -a (names only) =="; docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"'

run 'echo "== containers exposing host ports (should be ONLY nginx later) =="; docker ps --format "{{.Names}}\t{{.Ports}}" | egrep -v "\t$" | egrep -v "^\s*$" || true'

# --- Docker: find anything listening internally for 8000/5432 by inspection ---
run 'echo "== inspect port bindings (all containers) =="; for c in $(docker ps -aq); do n=$(docker inspect -f "{{.Name}}" "$c" | sed "s#/##"); pb=$(docker inspect -f "{{json .HostConfig.PortBindings}}" "$c"); echo "$n $pb"; done'

# --- Docker: find containers that include API-ish words in cmd/entrypoint ---
run 'echo "== API-ish docker entrypoints/cmd =="; for n in $(docker ps --format "{{.Names}}"); do echo "--- $n ---"; docker inspect -f "Image={{.Config.Image}} Entrypoint={{json .Config.Entrypoint}} Cmd={{json .Config.Cmd}}" "$n"; done | egrep -i "truckerp|uvicorn|gunicorn|fastapi|nginx|caddy|traefik|python" || true'

# --- Docker networks (confirm truckerp_net membership) ---
run 'echo "== docker networks =="; docker network ls'
run 'echo "== who is on truckerp_net =="; docker network inspect truckerp_net --format "{{range \$k,\$v := .Containers}}{{println \$v.Name}}{{end}}" 2>/dev/null | sort || true'

# --- Repo sanity: where are we, what compose files exist ---
run 'echo "== repo dir listing (top) =="; ls -la /home/admin/trucking_erp | sed -n "1,200p"'
run 'echo "== compose files found =="; ls -la /home/admin/trucking_erp | egrep -i "docker-compose|compose|\.yml|\.yaml" || true'

# --- Env leaks prevention: only show keys, redact values if printed ---
run 'echo "== docker env keys for truckerp-api (no values) =="; docker inspect -f "{{range .Config.Env}}{{println .}}{{end}}" truckerp-api 2>/dev/null | cut -d= -f1 | sort || true'

echo >>"$out"
echo "DONE. Output: $out"
echo "$out"
