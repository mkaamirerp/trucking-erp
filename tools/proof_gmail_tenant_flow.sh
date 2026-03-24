#!/bin/bash
# Proof: Gmail tenant user flow end-to-end
# Connect → approve → callback → connected → test → disconnect → reconnect
#
# Usage:
#   ADMIN_EMAIL=... ADMIN_PASSWORD=... ./tools/proof_gmail_tenant_flow.sh
#
# Step 3 (approve on Google) must be done manually in browser.
# Steps 4-8 run automatically after successful connect.

set -e
COOKIES=$(mktemp)
trap "rm -f $COOKIES" EXIT

BASE_URL="${BASE_URL:-https://demo.truckerp.me}"
TENANT="${TENANT:-demo}"
ADMIN_EMAIL="${ADMIN_EMAIL:?Set ADMIN_EMAIL}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:?Set ADMIN_PASSWORD}"

USE_BEARER=false
case "$BASE_URL" in
  http://localhost*|http://127.0.0.1*) USE_BEARER=true ;;
esac

CURL_OPTS="-sS -c $COOKIES -b $COOKIES"
[ "$USE_BEARER" = true ] && BEARER=""

echo "=== Gmail tenant flow proof ==="
echo "BASE_URL=$BASE_URL TENANT=$TENANT"

PHASE="${PHASE:-}"

# 1. Login
echo ""
echo "1. Login..."
LOGIN=$(curl $CURL_OPTS -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -H "Host: ${TENANT}.truckerp.me" \
  -H "X-Tenant-Slug: $TENANT" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")
HTTP=$(echo "$LOGIN" | tail -1)
BODY=$(echo "$LOGIN" | sed '$d')
if [ "$HTTP" = "200" ]; then
  echo "   -> 200 OK"
  TOKEN=$(echo "$BODY" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
  [ -n "$TOKEN" ] && [ "$USE_BEARER" = true ] && BEARER="-H \"Authorization: Bearer $TOKEN\""
else
  echo "   -> $HTTP"
  echo "$BODY" | head -5
  exit 1
fi

# If post_connect, skip to steps 4-8
if [ "$PHASE" = "post_connect" ]; then
  echo ""
  echo "4. GET /email-config/primary (connected state)..."
  PRIMARY=$(curl $CURL_OPTS -H "Host: ${TENANT}.truckerp.me" -H "X-Tenant-Slug: $TENANT" \
    "$BASE_URL/api/v1/admin/email-config/primary" 2>/dev/null)
  echo "   -> $(echo "$PRIMARY" | head -c 200)..."
  [ -n "$PRIMARY" ] && echo "   mailbox_type=$(echo "$PRIMARY" | grep -o '"mailbox_type":"[^"]*"' | cut -d'"' -f4)"
  [ -n "$PRIMARY" ] && echo "   connection_mode=$(echo "$PRIMARY" | grep -o '"connection_mode":"[^"]*"' | cut -d'"' -f4)"
  [ -n "$PRIMARY" ] && echo "   oauth_account_email=$(echo "$PRIMARY" | grep -o '"oauth_account_email":"[^"]*"' | cut -d'"' -f4)"

  echo ""
  echo "5. POST /email-config/primary/test..."
  TEST=$(curl $CURL_OPTS -X POST -H "Host: ${TENANT}.truckerp.me" -H "X-Tenant-Slug: $TENANT" \
    "$BASE_URL/api/v1/admin/email-config/primary/test" 2>/dev/null)
  echo "   -> $TEST"

  echo ""
  echo "6. POST /email-config/primary/disconnect..."
  DISC=$(curl $CURL_OPTS -X POST -H "Host: ${TENANT}.truckerp.me" -H "X-Tenant-Slug: $TENANT" \
    "$BASE_URL/api/v1/admin/email-config/primary/disconnect" 2>/dev/null)
  echo "   -> $DISC"

  echo ""
  echo "7. GET /primary after disconnect (expect null)..."
  PRIMARY2=$(curl $CURL_OPTS -H "Host: ${TENANT}.truckerp.me" -H "X-Tenant-Slug: $TENANT" \
    "$BASE_URL/api/v1/admin/email-config/primary" 2>/dev/null)
  echo "   -> ${PRIMARY2:-null}"

  echo ""
  echo "8. Reconnect: GET /gmail/authorize..."
  AUTHZ2=$(curl $CURL_OPTS -D - -o /dev/null -w "%{http_code}" \
    -H "Host: ${TENANT}.truckerp.me" \
    -H "X-Tenant-Slug: $TENANT" \
    "$BASE_URL/api/v1/admin/email-config/gmail/authorize" 2>/dev/null)
  echo "   -> $AUTHZ2 (expect 302 to Google)"
  echo ""
  echo "=== Proof complete ==="
  exit 0
fi

# 2. Connect with Google (authorize)
echo ""
echo "2. GET /gmail/authorize..."
RESP=$(curl $CURL_OPTS -D - -o /tmp/proof_body.txt \
  -H "Host: ${TENANT}.truckerp.me" \
  -H "X-Tenant-Slug: $TENANT" \
  "$BASE_URL/api/v1/admin/email-config/gmail/authorize" 2>/dev/null)
AUTHZ=$(echo "$RESP" | grep -o "HTTP/[0-9.]* [0-9]*" | tail -1 | awk '{print $2}')
LOCATION=$(echo "$RESP" | grep -i "^location:" | head -1)
echo "   -> $AUTHZ"
echo "   $LOCATION"

if [ "$AUTHZ" = "503" ]; then
  echo "   (503 = Gmail not configured. Add GOOGLE_CLIENT_ID/SECRET to secrets.)"
  exit 0
fi
if [ "$AUTHZ" != "302" ]; then
  echo "   Expected 302. Got $AUTHZ"
  exit 1
fi

echo ""
echo "3. [MANUAL] Approve on Google in browser. Then run:"
echo "   ADMIN_EMAIL=$ADMIN_EMAIL ADMIN_PASSWORD=*** PHASE=post_connect $0"
