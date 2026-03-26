#!/bin/bash
# Manual test: Multi-role onboarding MVP
# Confirms: invite rows store application_type + requested_role_code;
#           DRIVER approval → PersonRole(DRIVER) + DriverProfile;
#           DISPATCHER approval → PersonRole(DISPATCHER), no DriverProfile.
#
# Usage:
#   BASE_URL=https://demo.truckerp.me TENANT=demo ADMIN_EMAIL=... ADMIN_PASSWORD=... ./tools/manual_test_multi_role_onboarding.sh
# Or for local: BASE_URL=http://localhost TENANT=demo ADMIN_EMAIL=... ADMIN_PASSWORD=...
#
# Prereqs: API running, demo tenant exists, admin user can log in.
# Note: For localhost, uses Bearer token (cookies set Domain=.truckerp.me).

set -e
COOKIES=$(mktemp)
trap "rm -f $COOKIES" EXIT

BASE_URL="${BASE_URL:-https://demo.truckerp.me}"
TENANT="${TENANT:-demo}"
ADMIN_EMAIL="${ADMIN_EMAIL:?Set ADMIN_EMAIL}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:?Set ADMIN_PASSWORD}"

# Use Bearer token for localhost (cookies use Domain=.truckerp.me and won't be sent to localhost)
USE_BEARER=false
case "$BASE_URL" in
  http://localhost*|http://127.0.0.1*) USE_BEARER=true ;;
esac

echo "=== Multi-role onboarding manual test ==="
echo "BASE_URL=$BASE_URL TENANT=$TENANT"

# 1. Login
echo ""
echo "1. Login as admin..."
LOGIN=$(curl -sS -c "$COOKIES" -b "$COOKIES" -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -H "Host: ${TENANT}.truckerp.me" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")
if echo "$LOGIN" | grep -q "access_token"; then
  echo "   Login OK"
  if [ "$USE_BEARER" = true ]; then
    AUTH_TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
    AUTH_HEADER="Authorization: Bearer $AUTH_TOKEN"
  fi
else
  echo "   Login failed: $LOGIN"
  exit 1
fi

# Common curl opts for admin requests: cookies or Bearer
_admin_curl() {
  if [ "$USE_BEARER" = true ]; then
    curl -sS "$@" -H "$AUTH_HEADER"
  else
    curl -sS -c "$COOKIES" -b "$COOKIES" "$@"
  fi
}

# 2. Create DRIVER invite
echo ""
echo "2. Create DRIVER invite..."
INVITE_DRIVER=$(_admin_curl -X POST "$BASE_URL/api/v1/admin/onboarding/invite-link" \
  -H "Content-Type: application/json" \
  -H "Host: ${TENANT}.truckerp.me" \
  -d '{"email":"driver-test@demo.test","application_type":"DRIVER"}')
APP_DRIVER=$(echo "$INVITE_DRIVER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('application_id','')); print(d.get('token',''))" 2>/dev/null | tr '\n' ' ')
APP_DRIVER_ID=$(echo "$APP_DRIVER" | cut -d' ' -f1)
TOKEN_DRIVER=$(echo "$APP_DRIVER" | cut -d' ' -f2)
if [ -z "$APP_DRIVER_ID" ] || [ -z "$TOKEN_DRIVER" ]; then
  echo "   Invite failed: $INVITE_DRIVER"
  exit 1
fi
echo "   DRIVER app_id=$APP_DRIVER_ID token=${TOKEN_DRIVER:0:8}..."

# 3. Create DISPATCHER invite
echo ""
echo "3. Create DISPATCHER invite..."
INVITE_DISP=$(_admin_curl -X POST "$BASE_URL/api/v1/admin/onboarding/invite-link" \
  -H "Content-Type: application/json" \
  -H "Host: ${TENANT}.truckerp.me" \
  -d '{"email":"dispatcher-test@demo.test","application_type":"DISPATCHER"}')
APP_DISP=$(echo "$INVITE_DISP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('application_id','')); print(d.get('token',''))" 2>/dev/null | tr '\n' ' ')
APP_DISP_ID=$(echo "$APP_DISP" | cut -d' ' -f1)
TOKEN_DISP=$(echo "$APP_DISP" | cut -d' ' -f2)
if [ -z "$APP_DISP_ID" ] || [ -z "$TOKEN_DISP" ]; then
  echo "   Invite failed: $INVITE_DISP"
  exit 1
fi
echo "   DISPATCHER app_id=$APP_DISP_ID token=${TOKEN_DISP:0:8}..."

# 4. Applicant submit DRIVER (intake_payload has first_name, last_name + driver fields)
echo ""
echo "4. Applicant submit DRIVER (token auth, no session)..."
DRIVER_SUBMIT=$(curl -sS -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/driver-onboarding/applicant/application/intake?token=$TOKEN_DRIVER" \
  -H "Content-Type: application/json" \
  -H "Host: ${TENANT}.truckerp.me" \
  -d '{"intake_payload":{"first_name":"Driver","last_name":"Test","driver_license_number":"DL123","license_region":"CA","license_expiry":"2028-12-31","step":"complete"},"submit":true}')
DRIVER_HTTP=$(echo "$DRIVER_SUBMIT" | tail -1)
echo "   Status: $DRIVER_HTTP"
if [ "$DRIVER_HTTP" != "200" ]; then
  echo "   Response: $(echo "$DRIVER_SUBMIT" | head -n -1)"
  exit 1
fi

# 5. Applicant submit DISPATCHER (minimal common intake)
echo ""
echo "5. Applicant submit DISPATCHER..."
DISP_SUBMIT=$(curl -sS -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/driver-onboarding/applicant/application/intake?token=$TOKEN_DISP" \
  -H "Content-Type: application/json" \
  -H "Host: ${TENANT}.truckerp.me" \
  -d '{"intake_payload":{"first_name":"Dispatcher","last_name":"Test","step":"common"},"submit":true}')
DISP_HTTP=$(echo "$DISP_SUBMIT" | tail -1)
echo "   Status: $DISP_HTTP"
if [ "$DISP_HTTP" != "200" ]; then
  echo "   Response: $(echo "$DISP_SUBMIT" | head -n -1)"
  exit 1
fi

# 6. Admin approve DRIVER
echo ""
echo "6. Admin approve DRIVER application..."
APPROVE_DRIVER=$(_admin_curl -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/driver-onboarding/applications/$APP_DRIVER_ID/approve" \
  -H "Host: ${TENANT}.truckerp.me")
APPROVE_DRIVER_HTTP=$(echo "$APPROVE_DRIVER" | tail -1)
echo "   Status: $APPROVE_DRIVER_HTTP"
if [ "$APPROVE_DRIVER_HTTP" != "200" ]; then
  echo "   Response: $(echo "$APPROVE_DRIVER" | head -n -1)"
  exit 1
fi

# 7. Admin approve DISPATCHER
echo ""
echo "7. Admin approve DISPATCHER application..."
APPROVE_DISP=$(_admin_curl -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/driver-onboarding/applications/$APP_DISP_ID/approve" \
  -H "Host: ${TENANT}.truckerp.me")
APPROVE_DISP_HTTP=$(echo "$APPROVE_DISP" | tail -1)
echo "   Status: $APPROVE_DISP_HTTP"
if [ "$APPROVE_DISP_HTTP" != "200" ]; then
  echo "   Response: $(echo "$APPROVE_DISP" | head -n -1)"
  exit 1
fi

echo ""
echo "=== API flow complete. Run DB verification: ==="
echo ""
echo "  APP_DRIVER_ID=$APP_DRIVER_ID APP_DISP_ID=$APP_DISP_ID ./tools/verify_multi_role_db.sh"
echo ""
echo "Or run the SQL manually (see verify_multi_role_db.sh)."
