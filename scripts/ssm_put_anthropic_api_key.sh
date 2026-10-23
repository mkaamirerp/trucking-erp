#!/usr/bin/env bash
# Store Claude (Anthropic) API key in SSM for this stack.
# Loaded at API start: scripts/start_api_with_ssm.sh → /run/secrets/truckerp.env → ANTHROPIC_API_KEY
#
# Recommended (prompts inside script — avoids export/shell quoting issues):
#   cd /home/admin/trucking_erp && SSM_ENV=prod ./scripts/ssm_put_anthropic_api_key.sh
#
# Or pass via env without spaces around = (use ASCII quotes only):
#   ANTHROPIC_API_KEY=sk-ant-api03-... SSM_ENV=prod ./scripts/ssm_put_anthropic_api_key.sh
#
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SSM_ENV="${SSM_ENV:-prod}"
NAME="/truckerp/${SSM_ENV}/platform/ANTHROPIC_API_KEY"

trim_key() {
  python3 -c 'import sys; print(sys.stdin.read().strip(), end="")'
}

read_key_interactive() {
  echo "Paste Anthropic API key (input hidden), then press Enter:" >&2
  local raw
  IFS= read -rs raw || true
  echo >&2
  printf '%s' "$raw" | trim_key
}

KEY="${ANTHROPIC_API_KEY:-}"
if [ -z "$KEY" ]; then
  KEY="$(read_key_interactive)"
fi
KEY="$(printf '%s' "$KEY" | trim_key)"

if [ -z "$KEY" ]; then
  echo "ERROR: API key is empty. Get one from Anthropic Console → API keys." >&2
  exit 1
fi
case "$KEY" in
  sk-ant-* ) ;;
  * )
    echo "WARNING: Key does not start with sk-ant- (continuing anyway)." >&2
    ;;
esac

aws ssm put-parameter \
  --name "$NAME" \
  --value "$KEY" \
  --type SecureString \
  --overwrite \
  --region "$REGION"

echo "Stored $NAME (SecureString). Restart truckerp-api:"
echo "  docker compose -f docker-compose.yml restart truckerp-api"
