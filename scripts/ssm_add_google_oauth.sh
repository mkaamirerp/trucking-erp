#!/usr/bin/env bash
# Add Google OAuth credentials from JSON file. Writes to .google_oauth.local (used by API startup).
# Usage: ./scripts/ssm_add_google_oauth.sh path/to/client_secret_xxx.json
# Or:   ./scripts/ssm_add_google_oauth.sh  (uses SSM_PUSH=1 to also push to SSM)

set -e
REGION="${AWS_REGION:-us-east-1}"
SSM_PREFIX="${SSM_PREFIX:-/truckerp/prod/platform}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

JSON_FILE="${1:-$GOOGLE_JSON}"
if [ -z "$JSON_FILE" ] || [ ! -f "$JSON_FILE" ]; then
  echo "Usage: $0 path/to/client_secret_xxx.json"
  exit 1
fi

CLIENT_ID=$(jq -r '.web.client_id // .installed.client_id // empty' "$JSON_FILE")
CLIENT_SECRET=$(jq -r '.web.client_secret // .installed.client_secret // empty' "$JSON_FILE")

if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
  echo "Could not find client_id or client_secret in $JSON_FILE"
  exit 1
fi

OUT="$REPO_ROOT/.google_oauth.local"
echo "GOOGLE_CLIENT_ID=$CLIENT_ID" > "$OUT"
echo "GOOGLE_CLIENT_SECRET=$CLIENT_SECRET" >> "$OUT"
echo "Wrote $OUT"

if [ "${SSM_PUSH:-0}" = "1" ]; then
  aws ssm put-parameter --name "${SSM_PREFIX}/GOOGLE_CLIENT_ID" --value "$CLIENT_ID" --type SecureString --overwrite --region "$REGION"
  aws ssm put-parameter --name "${SSM_PREFIX}/GOOGLE_CLIENT_SECRET" --value "$CLIENT_SECRET" --type SecureString --overwrite --region "$REGION"
  echo "Also pushed to SSM $SSM_PREFIX"
fi
echo "Restart API: docker compose -f docker-compose.yml up -d --force-recreate truckerp-api"