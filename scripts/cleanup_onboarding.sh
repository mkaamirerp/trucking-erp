#!/usr/bin/env bash
# Run onboarding cleanup (old OTP tokens + old drafts) inside the API container with platform DB env.
# For cron: run without -it. For manual run: same script or use ./scripts/db_run.sh "python -m app.scripts.cleanup_onboarding"
set -euo pipefail

ENV_FILE="${ENV_FILE:-/run/secrets/truckerp.env}"
CONTAINER="${CONTAINER:-truckerp-api}"

if ! docker exec "$CONTAINER" test -f "$ENV_FILE" 2>/dev/null; then
  echo "ERROR: $ENV_FILE not found inside $CONTAINER. Run ./scripts/start_api_with_ssm.sh first."
  exit 1
fi

# Optional: set CLEANUP_DRY_RUN=false to actually delete (e.g. in cron)
# OTP_RETENTION_DAYS=30, DRAFT_RETENTION_DAYS=14 (override via env if needed)
docker exec "$CONTAINER" sh -lc "
  set -a
  . $ENV_FILE
  set +a
  python -m app.scripts.cleanup_onboarding
"
