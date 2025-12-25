#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
API="${API:-$BASE_URL/api/v1}"

# ========== helpers ==========
hr() { printf "\n============================================================\n"; }
subhr() { printf "\n------------------------------\n"; }
ok() { printf "✅ %s\n" "$1"; }
warn() { printf "⚠️  %s\n" "$1"; }
fail() { printf "❌ %s\n" "$1" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing dependency: $1"
}

curl_json() {
  curl -sS --max-time 8 "$@"
}

http_code() {
  curl -sS -o /dev/null --max-time 8 -w "%{http_code}" "$@"
}

json_type_is() {
  local json="$1" t="$2"
  echo "$json" | jq -e --arg t "$t" 'type==$t' >/dev/null
}

json_has_key() {
  local json="$1" key="$2"
  echo "$json" | jq -e --arg k "$key" 'has($k)' >/dev/null
}

count_array() {
  local json="$1"
  echo "$json" | jq 'length'
}

# ========== start ==========
need_cmd jq
need_cmd curl
need_cmd grep
need_cmd sed

hr
echo "Trucking ERP EXTENDED Smoke Test"
echo "BASE_URL=$BASE_URL"
echo "API=$API"
echo "Time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# ---------- 1) Health ----------
hr
echo "1) Health endpoint"
health="$(curl_json "$API/health")"
echo "$health" | jq .
echo "$health" | jq -e '.status=="ok"' >/dev/null && ok "Health OK" || fail "Health failed"

# ---------- 2) OpenAPI ----------
hr
echo "2) OpenAPI sanity"
code_openapi="$(http_code "$BASE_URL/openapi.json")"
echo "GET /openapi.json => HTTP $code_openapi"
[[ "$code_openapi" == "200" ]] && ok "OpenAPI reachable" || warn "OpenAPI not reachable (not fatal)"

# ---------- 3) Drivers default ----------
hr
echo "3) Drivers list (default: active only)"
drivers_active="$(curl_json "$API/drivers")"
echo "$drivers_active" | jq .
json_type_is "$drivers_active" "array" && ok "Drivers default returns array" || fail "Drivers default did not return array"
active_count="$(count_array "$drivers_active")"
ok "Active count: $active_count"

# ---------- 4) Drivers include inactive ----------
hr
echo "4) Drivers list (include_inactive=true)"
drivers_all="$(curl_json "$API/drivers?include_inactive=true")"
echo "$drivers_all" | jq .
json_type_is "$drivers_all" "array" && ok "Drivers all returns array" || fail "Drivers all did not return array"
total_count="$(count_array "$drivers_all")"
inactive_count="$(echo "$drivers_all" | jq '[.[] | select(.is_active==false)] | length')"
ok "Total: $total_count | Active: $active_count | Inactive: $inactive_count"

if [[ "$total_count" -lt "$active_count" ]]; then
  fail "Logic error: total_count < active_count"
fi

# ---------- 5) "Missing drivers" explanation ----------
hr
echo "5) UX logic: explain 'missing drivers' scenario"
if [[ "$active_count" -eq 0 && "$total_count" -gt 0 ]]; then
  warn "No active drivers but inactive exist. Default hides inactive (ops-correct)."
  echo "Frontend later: show meta(total/returned/include_inactive) so user understands."
else
  ok "Either active drivers exist or there are no drivers at all."
fi

# ---------- 6) Verify required driver fields exist ----------
hr
echo "6) Validate driver fields shape"
if [[ "$total_count" -gt 0 ]]; then
  # pick first driver in all list
  echo "$drivers_all" | jq '.[0]' >/tmp/driver0.json
  d0="$(cat /tmp/driver0.json)"
  echo "$d0" | jq .
  for k in id first_name last_name is_active; do
    echo "$d0" | jq -e --arg k "$k" 'has($k)' >/dev/null || fail "Driver missing key: $k"
  done
  ok "Driver required keys present"
else
  warn "No drivers exist yet; shape checks limited."
fi

# ---------- 7) Negative test: invalid driver create (expect 422) ----------
hr
echo "7) Negative test: create driver with missing required fields (expect 422)"
code_bad_driver="$(http_code -X POST "$API/drivers" -H "Content-Type: application/json" -d '{"first_name":""}')"
echo "POST /drivers bad payload => HTTP $code_bad_driver (expected 422)"
[[ "$code_bad_driver" == "422" ]] && ok "Validation works (422)" || warn "Expected 422, got $code_bad_driver"

# ---------- 8) Create a new active test driver (if needed) ----------
hr
echo "8) Ensure we have at least 1 active driver for doc tests"
ACTIVE_DRIVER_ID="$(echo "$drivers_active" | jq -r '.[0].id // empty')"
if [[ -z "$ACTIVE_DRIVER_ID" ]]; then
  warn "No active driver found. Creating one for smoke test..."
  new_driver_payload='{"first_name":"Smoke","last_name":"Test","email":"smoke.test@example.com","phone":"4165559999","hire_date":"2025-01-01","is_active":true}'
  created_driver="$(curl_json -X POST "$API/drivers" -H "Content-Type: application/json" -d "$new_driver_payload")"
  echo "$created_driver" | jq .
  ACTIVE_DRIVER_ID="$(echo "$created_driver" | jq -r '.id // empty')"
  [[ -n "$ACTIVE_DRIVER_ID" ]] && ok "Created active driver id=$ACTIVE_DRIVER_ID" || fail "Could not create active driver"
else
  ok "Using existing active driver id=$ACTIVE_DRIVER_ID"
fi

# ---------- 9) Driver documents list ----------
hr
echo "9) List documents for active driver"
docs_before="$(curl_json "$API/driver-documents/$ACTIVE_DRIVER_ID")"
echo "$docs_before" | jq .
json_type_is "$docs_before" "array" && ok "Docs list returns array" || fail "Docs list did not return array"
docs_before_count="$(count_array "$docs_before")"
ok "Docs before count: $docs_before_count"

# ---------- 10) Negative test: bad doc payload (expect 422) ----------
hr
echo "10) Negative test: create doc with invalid date (expect 422)"
bad_doc_payload='{"doc_type":"CDL","title":"Bad Date","issue_date":"not-a-date","expiry_date":"2026-01-01","status":"ACTIVE","notes":"smoke"}'
code_bad_doc="$(http_code -X POST "$API/driver-documents/$ACTIVE_DRIVER_ID" -H "Content-Type: application/json" -d "$bad_doc_payload")"
echo "POST doc bad payload => HTTP $code_bad_doc (expected 422)"
[[ "$code_bad_doc" == "422" ]] && ok "Doc validation works (422)" || warn "Expected 422, got $code_bad_doc"

# ---------- 11) Create a CDL doc ----------
hr
echo "11) Create a CDL doc for active driver"
doc_payload='{"doc_type":"CDL","title":"Smoke CDL","issue_date":"2024-01-01","expiry_date":"2026-01-01","status":"ACTIVE","notes":"extended smoke_test.sh"}'
created_doc="$(curl_json -X POST "$API/driver-documents/$ACTIVE_DRIVER_ID" -H "Content-Type: application/json" -d "$doc_payload")"
echo "$created_doc" | jq .
DOC_ID="$(echo "$created_doc" | jq -r '.id // empty')"
[[ -n "$DOC_ID" ]] && ok "Created doc id=$DOC_ID" || fail "Doc create failed (no id)"
echo "$created_doc" | jq -e '.is_current==true' >/dev/null && ok "Doc is_current=true" || warn "Doc is_current not true (check logic)"

# ---------- 12) List docs again & verify presence ----------
hr
echo "12) List docs again; verify created doc is present"
docs_after="$(curl_json "$API/driver-documents/$ACTIVE_DRIVER_ID")"
echo "$docs_after" | jq .
docs_after_count="$(count_array "$docs_after")"
ok "Docs after count: $docs_after_count"
echo "$docs_after" | jq -e --argjson id "$DOC_ID" 'map(select(.id==$id)) | length == 1' >/dev/null \
  && ok "Created doc appears in list" || fail "Created doc missing from list"

# ---------- 13) Compliance: no hard delete endpoints ----------
hr
echo "13) Compliance: hard DELETE should not be supported (expect 404/405)"
set +e
del_driver_code="$(http_code -X DELETE "$API/drivers/$ACTIVE_DRIVER_ID")"
del_doc_code="$(http_code -X DELETE "$API/driver-documents/$ACTIVE_DRIVER_ID/$DOC_ID")"
set -e
echo "DELETE /drivers/$ACTIVE_DRIVER_ID => HTTP $del_driver_code (expected 404/405)"
echo "DELETE /driver-documents/...     => HTTP $del_doc_code (expected 404/405)"
[[ "$del_driver_code" == "404" || "$del_driver_code" == "405" ]] && ok "Driver hard-delete not available (good)" || warn "Unexpected driver DELETE code: $del_driver_code"
[[ "$del_doc_code" == "404" || "$del_doc_code" == "405" ]] && ok "Doc hard-delete not available (good)" || warn "Unexpected doc DELETE code: $del_doc_code"

# ---------- 14) Soft termination behavior (if endpoint exists) ----------
hr
echo "14) Soft-termination test (only if PUT/PATCH endpoint exists)"
echo "We should NOT delete drivers. We deactivate instead for compliance."
# Probe common endpoints (PATCH then PUT). If neither exists, we skip.
set +e
patch_code="$(http_code -X PATCH "$API/drivers/$ACTIVE_DRIVER_ID" -H "Content-Type: application/json" -d '{"is_active":false,"termination_date":"2025-12-24"}')"
put_code="$(http_code -X PUT "$API/drivers/$ACTIVE_DRIVER_ID" -H "Content-Type: application/json" -d '{"is_active":false,"termination_date":"2025-12-24"}')"
set -e

if [[ "$patch_code" == "200" || "$patch_code" == "204" ]]; then
  ok "PATCH deactivate supported (HTTP $patch_code)"
elif [[ "$put_code" == "200" || "$put_code" == "204" ]]; then
  ok "PUT deactivate supported (HTTP $put_code)"
else
  warn "No update endpoint yet (PATCH=$patch_code, PUT=$put_code). Skipping deactivate test."
fi

# If deactivate worked, confirm active list changes (best effort)
if [[ "$patch_code" == "200" || "$patch_code" == "204" || "$put_code" == "200" || "$put_code" == "204" ]]; then
  subhr
  echo "14b) Confirm driver removed from active list but still present in include_inactive list"
  drivers_active2="$(curl_json "$API/drivers")"
  drivers_all2="$(curl_json "$API/drivers?include_inactive=true")"
  echo "$drivers_active2" | jq .
  echo "$drivers_all2" | jq .
  echo "$drivers_active2" | jq -e --argjson id "$ACTIVE_DRIVER_ID" 'map(select(.id==$id))|length==0' >/dev/null \
    && ok "Driver no longer in active list (expected)" || warn "Driver still in active list (check deactivate logic)"
  echo "$drivers_all2" | jq -e --argjson id "$ACTIVE_DRIVER_ID" 'map(select(.id==$id))|length==1' >/dev/null \
    && ok "Driver still exists in include_inactive list (compliance OK)" || warn "Driver missing from include_inactive list (NOT OK)"
fi

# ---------- 15) Canonical DB drift guard (repo-level) ----------
hr
echo "15) Canonical DB drift guard (repo scan)"
echo "Ensure no router imports app.db.session.get_db"
if grep -R "from app\.db\.session import get_db" -n app >/dev/null 2>&1; then
  grep -R "from app\.db\.session import get_db" -n app || true
  fail "DB drift detected: routers still importing app.db.session.get_db"
else
  ok "No routers import deprecated app.db.session.get_db"
fi

echo "Ensure deprecated module is fail-fast"
if grep -R "app\.db\.session is deprecated" -n app/db/session.py >/dev/null 2>&1; then
  ok "Deprecated session module has guard message"
else
  warn "Deprecated session module guard message not found (check app/db/session.py)"
fi

# ---------- 16) Summary ----------
hr
ok "EXTENDED SMOKE TEST COMPLETE"
echo "Notes:"
echo "- No hard deletes were performed."
echo "- If driver update endpoints are not implemented yet, deactivate tests are skipped."

# ---------- 17) Driver-documents endpoint: must be driver-specific ----------
hr
echo "17) Route sanity: /driver-documents (no id) should NOT exist"
code_docs_root="$(http_code "$API/driver-documents")"
echo "GET /driver-documents => HTTP $code_docs_root (expected 404)"
[[ "$code_docs_root" == "404" ]] && ok "Docs root not found (good)" || warn "Unexpected docs root code: $code_docs_root"

# ---------- 18) Docs list should include required keys ----------
hr
echo "18) Validate document fields shape (if any docs exist)"
docs_now="$(curl_json "$API/driver-documents/$ACTIVE_DRIVER_ID")"
echo "$docs_now" | jq .
docs_now_count="$(count_array "$docs_now")"
ok "Docs current count: $docs_now_count"

if [[ "$docs_now_count" -gt 0 ]]; then
  doc0="$(echo "$docs_now" | jq '.[0]')"
  for k in id driver_id doc_type title status is_current created_at updated_at; do
    echo "$doc0" | jq -e --arg k "$k" 'has($k)' >/dev/null || fail "Document missing key: $k"
  done
  ok "Document required keys present"
else
  warn "No docs to validate shape (not fatal)"
fi

# ---------- 19) Docs 'is_current' logic (should be at least one current for CDL after creates) ----------
hr
echo "19) Validate is_current behavior for CDL (best-effort)"
current_cdl_count="$(echo "$docs_now" | jq '[.[] | select(.doc_type=="CDL" and .is_current==true)] | length')"
echo "Current CDL count: $current_cdl_count"
if [[ "$current_cdl_count" -ge 1 ]]; then
  ok "At least one CDL is marked is_current=true"
else
  warn "No CDL marked is_current=true (might be expected if logic not implemented)"
fi

# ---------- 20) Duplicate CDL create test (should ideally not create multiple current CDLs) ----------
hr
echo "20) Create another CDL and see if 'current' is enforced (NO deletes)"
doc_payload2='{"doc_type":"CDL","title":"Smoke CDL v2","issue_date":"2024-02-01","expiry_date":"2026-02-01","status":"ACTIVE","notes":"duplicate CDL test"}'
created_doc2="$(curl_json -X POST "$API/driver-documents/$ACTIVE_DRIVER_ID" -H "Content-Type: application/json" -d "$doc_payload2")"
echo "$created_doc2" | jq .
DOC2_ID="$(echo "$created_doc2" | jq -r '.id // empty')"
if [[ -n "$DOC2_ID" ]]; then
  ok "Created second CDL doc id=$DOC2_ID"
else
  warn "Second CDL create did not return id (check API behavior)"
fi

docs_after2="$(curl_json "$API/driver-documents/$ACTIVE_DRIVER_ID")"
echo "$docs_after2" | jq .
current_cdl_count2="$(echo "$docs_after2" | jq '[.[] | select(.doc_type=="CDL" and .is_current==true)] | length')"
echo "Current CDL count after second create: $current_cdl_count2"

if [[ "$current_cdl_count2" -le 1 ]]; then
  ok "Current CDL enforcement looks good (<= 1 current)"
else
  warn "Multiple current CDLs detected ($current_cdl_count2). Not a failure yet, but Phase 9.6 should enforce one-current rule."
fi

# ---------- 21) Docs ordering sanity (newer docs should usually appear last or first consistently) ----------
hr
echo "21) Docs ordering sanity (created_at monotonic check - best-effort)"
if [[ "$(count_array "$docs_after2")" -ge 2 ]]; then
  # Check if sorted by created_at ASC or DESC; we just warn if it's chaotic
  is_asc="$(echo "$docs_after2" | jq -r 'map(.created_at) as $t | ($t == ($t|sort))')"
  is_desc="$(echo "$docs_after2" | jq -r 'map(.created_at) as $t | ($t == ($t|sort|reverse))')"
  echo "created_at sorted ASC?  $is_asc"
  echo "created_at sorted DESC? $is_desc"
  if [[ "$is_asc" == "true" || "$is_desc" == "true" ]]; then
    ok "Docs ordering is consistent"
  else
    warn "Docs ordering is not consistently sorted by created_at (not fatal)"
  fi
else
  warn "Not enough docs to check ordering"
fi

# ---------- 22) Repeated health checks (stability smoke) ----------
hr
echo "22) Stability: run health check 5 times"
for i in 1 2 3 4 5; do
  h="$(curl_json "$API/health")"
  echo "health[$i] => $(echo "$h" | jq -r '.status // "?"')"
  echo "$h" | jq -e '.status=="ok"' >/dev/null || fail "Health failed on attempt $i"
done
ok "Repeated health checks passed"

# ---------- 23) Service status (best-effort; skips if not available) ----------
hr
echo "23) systemd service status (best-effort)"
if command -v systemctl >/dev/null 2>&1; then
  set +e
  systemctl is-active --quiet trucking_erp
  svc_code=$?
  set -e
  if [[ "$svc_code" == "0" ]]; then
    ok "systemd: trucking_erp is active"
  else
    warn "systemd: trucking_erp is not active (code $svc_code) — check: sudo systemctl status trucking_erp"
  fi
else
  warn "systemctl not available; skipping service status"
fi

# ---------- 24) Canonical DB files exist (repo sanity) ----------
hr
echo "24) Canonical DB files exist"
[[ -f app/core/config.py ]] && ok "app/core/config.py exists" || fail "Missing app/core/config.py"
[[ -f app/core/database.py ]] && ok "app/core/database.py exists" || fail "Missing app/core/database.py"

# ---------- 25) Final summary (extended) ----------
hr
ok "EXTENDED SMOKE TEST (v2) COMPLETE"
