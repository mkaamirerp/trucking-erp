#!/usr/bin/env bash
# Driver onboarding E2E proof: create invite token, then hit applicant API with curl.
# Run from repo root. Requires: docker compose API running, tenant "demo" (or SLUG) with DB.
# Usage: ./scripts/proof_driver_onboarding_e2e.sh [slug]

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SLUG="${1:-demo}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
API="${BASE_URL}/api/v1"

echo "=== Driver onboarding E2E proof (slug=$SLUG, base=$BASE_URL) ==="

# 1) Create proof token (run inside API container)
OUT=$(docker exec truckerp-api bash -lc "set -a && . /run/secrets/truckerp.env 2>/dev/null || true; set +a && cd /app && python -m app.scripts.create_proof_token $SLUG" 2>/dev/null)
if [[ -z "$OUT" ]]; then
  echo "FAIL: could not create proof token (tenant $SLUG missing or DB not ready?)"
  exit 1
fi
eval "$OUT"
if [[ -z "${PROOF_TOKEN:-}" ]]; then
  echo "FAIL: PROOF_TOKEN empty after create_proof_token"
  exit 1
fi
echo "Created proof token (length=${#PROOF_TOKEN})"

# 2) Health
echo ""
echo "--- GET /api/v1/health ---"
HTTP=$(curl -s -o /tmp/proof_health.json -w "%{http_code}" "$API/health")
if [[ "$HTTP" != "200" ]]; then
  echo "FAIL: health returned $HTTP"
  exit 1
fi
echo "OK $HTTP"

# 3) GET application by token
echo ""
echo "--- GET applicant/application?token=... ---"
HTTP=$(curl -s -o /tmp/proof_app.json -w "%{http_code}" -H "X-Tenant-Slug: $SLUG" "$API/driver-onboarding/applicant/application?token=$PROOF_TOKEN")
if [[ "$HTTP" != "200" ]]; then
  echo "FAIL: GET application returned $HTTP"
  cat /tmp/proof_app.json | head -5
  exit 1
fi
echo "OK $HTTP"

# 4) POST intake (save payload, no submit)
echo ""
echo "--- POST applicant/application/intake ---"
HTTP=$(curl -s -o /tmp/proof_intake.json -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" -H "X-Tenant-Slug: $SLUG" \
  -d '{"intake_payload":{"step":1,"first_name":"Proof","last_name":"User"},"submit":false}' \
  "$API/driver-onboarding/applicant/application/intake?token=$PROOF_TOKEN")
if [[ "$HTTP" != "200" ]]; then
  echo "FAIL: POST intake returned $HTTP"
  cat /tmp/proof_intake.json | head -5
  exit 1
fi
echo "OK $HTTP"

# 5) POST dl-upload (CDL_FRONT) with a tiny file
echo ""
echo "--- POST applicant/application/dl-upload (CDL_FRONT) ---"
TMP_DL="/tmp/proof_dl_front.bin"
printf '\x89PNG\r\n\x1a\n' > "$TMP_DL"
HTTP=$(curl -s -o /tmp/proof_dl_resp.json -w "%{http_code}" -X POST \
  -H "X-Tenant-Slug: $SLUG" \
  -F "doc_type=CDL_FRONT" -F "file=@$TMP_DL;filename=front.png" \
  "$API/driver-onboarding/applicant/application/dl-upload?token=$PROOF_TOKEN")
if [[ "$HTTP" != "200" ]]; then
  echo "FAIL: POST dl-upload returned $HTTP"
  cat /tmp/proof_dl_resp.json | head -5
  exit 1
fi
echo "OK $HTTP"
FILE_ID=$(jq -r '.intake_payload.files.CDL_FRONT.storage_key // empty' /tmp/proof_dl_resp.json)
if [[ -z "$FILE_ID" ]]; then
  echo "WARN: no storage_key in response (optional for proof)"
fi

# 6) GET file (if we have file_id)
if [[ -n "$FILE_ID" ]]; then
  echo ""
  echo "--- GET applicant/application/file?file_id=... ---"
  HTTP=$(curl -s -o /tmp/proof_file.bin -w "%{http_code}" -H "X-Tenant-Slug: $SLUG" \
    "$API/driver-onboarding/applicant/application/file?token=$PROOF_TOKEN&file_id=$FILE_ID")
  if [[ "$HTTP" != "200" ]]; then
    echo "FAIL: GET file returned $HTTP"
    exit 1
  fi
  echo "OK $HTTP (size $(wc -c < /tmp/proof_file.bin) bytes)"
fi

# 7) POST document-upload (e.g. dot_medical)
echo ""
echo "--- POST applicant/application/document-upload ---"
TMP_DOC="/tmp/proof_doc.bin"
echo "proof document" > "$TMP_DOC"
HTTP=$(curl -s -o /tmp/proof_doc_resp.json -w "%{http_code}" -X POST \
  -H "X-Tenant-Slug: $SLUG" \
  -F "doc_type=dot_medical" -F "file=@$TMP_DOC;filename=medical.pdf" \
  "$API/driver-onboarding/applicant/application/document-upload?token=$PROOF_TOKEN")
if [[ "$HTTP" != "200" ]]; then
  echo "FAIL: POST document-upload returned $HTTP"
  cat /tmp/proof_doc_resp.json | head -5
  exit 1
fi
echo "OK $HTTP"

# 8) POST intake submit
echo ""
echo "--- POST applicant/application/intake (submit=true) ---"
HTTP=$(curl -s -o /tmp/proof_submit.json -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" -H "X-Tenant-Slug: $SLUG" \
  -d '{"intake_payload":{"step":3,"first_name":"Proof","last_name":"User"},"submit":true}' \
  "$API/driver-onboarding/applicant/application/intake?token=$PROOF_TOKEN")
if [[ "$HTTP" != "200" ]]; then
  echo "FAIL: POST intake submit returned $HTTP"
  cat /tmp/proof_submit.json | head -5
  exit 1
fi
STATUS=$(jq -r '.status // empty' /tmp/proof_submit.json)
if [[ "$STATUS" != "SUBMITTED" ]]; then
  echo "FAIL: expected status SUBMITTED, got $STATUS"
  exit 1
fi
echo "OK $HTTP status=$STATUS"

echo ""
echo "=== E2E proof passed ==="
