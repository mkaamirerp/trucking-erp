#!/usr/bin/env bash
# Put LOGIN_TRUST_COOKIE_SECRET in SSM under the platform path (same tree as JWT_SECRET).
# API loads it via scripts/start_api_with_ssm.sh → /run/secrets/truckerp.env (Pydantic: login_trust_cookie_secret).
#
# Usage:
#   export LOGIN_TRUST_COOKIE_SECRET="$(openssl rand -hex 32)"   # or another long random secret
#   SSM_ENV=prod ./scripts/ssm_put_login_trust_cookie_secret.sh
#
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
SSM_ENV="${SSM_ENV:-prod}"
PREFIX="/truckerp/${SSM_ENV}/platform"
NAME="${PREFIX}/LOGIN_TRUST_COOKIE_SECRET"

if [ -z "${LOGIN_TRUST_COOKIE_SECRET:-}" ]; then
  echo "ERROR: Set LOGIN_TRUST_COOKIE_SECRET to a long random value before running (example: openssl rand -hex 32)." >&2
  exit 1
fi

aws ssm put-parameter \
  --name "$NAME" \
  --value "$LOGIN_TRUST_COOKIE_SECRET" \
  --type SecureString \
  --overwrite \
  --region "$REGION"

echo "Stored $NAME (SecureString). Restart truckerp-api so start_api_with_ssm.sh refetches parameters."
