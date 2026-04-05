#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/render_truckerp_env_from_ssm.sh"

docker compose up -d --force-recreate truckerp-api

if [[ "${CLEANUP:-0}" == "1" ]]; then
  # Best-effort: wait briefly for app to bind before cleaning up.
  for _ in $(seq 1 30); do
    if docker run --rm --network truckerp_net alpine:3.20 sh -lc \
      "apk add --no-cache curl >/dev/null && curl -sS -o /dev/null -w '%{http_code}' http://truckerp-api:8000/api/v1/health" \
      | grep -q '^200$'; then
      rm -f /home/admin/trucking_erp/runtime/rendered/truckerp.env
      break
    fi
    sleep 2
  done
fi
