#!/usr/bin/env bash
# Renew Gmail users.watch for tenants whose watch expires within the configured window.
# Schedule: e.g. every 12–24h on the EC2 host (cron) or a job runner that can docker exec truckerp-api with secrets.
# Requires GMAIL_PUBSUB_TOPIC_NAME in truckerp.env. Optional: GMAIL_WATCH_RENEW_BEFORE_HOURS, RENEW_GMAIL_FORCE=1.
set -euo pipefail

CONTAINER="${CONTAINER:-truckerp-api}"

if ! docker exec "$CONTAINER" test -f /run/secrets/truckerp.env 2>/dev/null; then
  echo "ERROR: /run/secrets/truckerp.env not found inside $CONTAINER." >&2
  exit 1
fi

docker exec "$CONTAINER" sh -lc '
  set -e
  set -a
  . /run/secrets/truckerp.env
  set +a
  cd /app
  exec python -m app.scripts.renew_gmail_watches
'
