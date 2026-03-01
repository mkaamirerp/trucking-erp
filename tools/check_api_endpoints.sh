#!/usr/bin/env bash
# Minimal API smoke checks. Run from API container with env loaded:
#   set -a && . /run/secrets/truckerp.env && set +a && /app/tools/check_api_endpoints.sh
set -e
BASE="${API_BASE:-http://127.0.0.1:8000}"
echo "Checking $BASE ..."
health=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/health" || true)
openapi=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/openapi.json" || true)
public_slug=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/public/check-slug-availability?slug=smoke99" || true)
echo "GET /api/v1/health     -> $health"
echo "GET /openapi.json     -> $openapi"
echo "GET /api/v1/public/check-slug-availability -> $public_slug"
fail=0
[ "$health" = "200" ] || { echo "FAIL: health"; fail=1; }
[ "$openapi" = "200" ] || { echo "FAIL: openapi"; fail=1; }
[ "$public_slug" = "200" ] || { echo "FAIL: public slug"; fail=1; }
[ $fail -eq 0 ] && echo "All checks passed." || exit 1
