#!/usr/bin/env bash
# Login, then GET /api/v1/me with Bearer token (no cookies).
# Usage: ./scripts/curl-me-with-login.sh <base_url> <tenant_id_or_slug> <email> <password>
# Example: ./scripts/curl-me-with-login.sh https://demo.truckerp.me 24 you@example.com yourpassword

set -e
BASE_URL="${1:?Usage: $0 <base_url> <tenant_id_or_slug> <email> <password>}"
TENANT="${2:?}"
EMAIL="${3:?}"
PASSWORD="${4:?}"

# Prefer X-Tenant-ID if numeric, else X-Tenant-Slug
if [[ "$TENANT" =~ ^[0-9]+$ ]]; then
  TENANT_HEADER="X-Tenant-ID: $TENANT"
else
  TENANT_HEADER="X-Tenant-Slug: $TENANT"
fi

# Login and extract access_token (requires jq)
RESP=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -H "$TENANT_HEADER" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

if ! TOKEN=$(echo "$RESP" | jq -r '.access_token'); then
  echo "Login failed or jq missing. Response: $RESP" >&2
  exit 1
fi

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "Login did not return access_token. Response: $RESP" >&2
  exit 1
fi

echo "Calling GET $BASE_URL/api/v1/me with Bearer token..."
curl -i "$BASE_URL/api/v1/me" \
  -H "Authorization: Bearer $TOKEN" \
  -H "$TENANT_HEADER"
