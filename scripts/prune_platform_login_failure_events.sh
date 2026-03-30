#!/usr/bin/env bash
# Prune platform_login_failure_events older than the retention window (platform DB).
# Schedule: e.g. daily on the EC2 host (cron) or any job runner that can docker exec truckerp-api with secrets.
set -euo pipefail

CONTAINER="${CONTAINER:-truckerp-api}"
ENV_FILE="/run/secrets/truckerp.env"

if ! docker exec "$CONTAINER" test -f "$ENV_FILE" 2>/dev/null; then
  echo "ERROR: $ENV_FILE not found inside $CONTAINER." >&2
  exit 1
fi

docker exec "$CONTAINER" sh -lc '
  set -e
  set -a
  if [ ! -f /run/secrets/truckerp.env ]; then
    echo "ERROR: /run/secrets/truckerp.env missing inside container." >&2
    exit 1
  fi
  . /run/secrets/truckerp.env
  set +a
  cd /app
  exec python -m app.scripts.prune_platform_login_failure_events "$@"
' _ "$@"
