# Milestone B1 — Attach Revised Rate Confirmation PDF

**Status:** **PASS** — implemented, verified on `https://demo.truckerp.me`, committed to `origin/gpt-review`. **STOP before B2.**

**Load under test:** tenant **demo** (`tenant_id=53`), **load ID 1010** (`load_number` Oct-26-0337), Armstrong shipment.

---

## Dispatcher step count (happy path)

| Phase | Steps |
|--------|--------|
| **Before B1** | No dedicated attach on the Load page; revised RC was not attach-first. |
| **After B1** | 1) Open Load → 2) **Attach revised PDF** → 3) Choose file. Attachment completes without **Save Load**; toolbar shows success and **Revised RC N** download links. |

---

## Final browser verification — new third revision (required)

This is the authoritative B1 frontend proof. Earlier runs against the Armstrong $2,000 fixture only hit **dedupe** because revisions 1–2 already used that SHA.

### Test fixture (test-only amendment)

| Field | Value |
|--------|--------|
| File | `docs/reports/milestone_b1_evidence/Armstrong_B1_revision3_test.pdf` |
| Description | Armstrong $2,000 PDF + ASCII PDF comment: B1 test-only amendment linehaul USD 2050 |
| SHA-256 | `d9d6436a3d96a61da2d6d8f7222a40da0c79b6e604f307c7b461b92c1d3e51c0` |
| Account | `fuel.e2e@truckerp.me` (Playwright) |
| Spec | `tests/e2e/milestone_b1_attach_third_revision.spec.ts` → **1 passed (~10.6s)** |

### Screenshots

| Step | File |
|------|------|
| Before third attach | `docs/reports/milestone_b1_screenshots/04-before-third-revision.png` |
| Success toast (no Save Load) | `docs/reports/milestone_b1_screenshots/05-after-third-revision-success.png` |
| After full page reload | `docs/reports/milestone_b1_screenshots/06-after-reload-third-revision.png` |
| After duplicate reattach | `docs/reports/milestone_b1_screenshots/07-after-duplicate-third-revision.png` |
| Earlier dedupe-only run ($2k fixture) | `01`–`03` in same directory |

### API responses (`stored_new`)

Captured in `docs/reports/milestone_b1_evidence/third_revision_api_responses.json`.

| Attempt | `stored_new` | `revision_index` | `pdf_reuse_status` | Message |
|---------|--------------|------------------|----------------------|---------|
| First attach (rev 3) | **true** | **3** | `new_revision` | Revised rate confirmation attached. |
| Reattach identical bytes | **false** | null | `existing_latest_revision` | This PDF is already accepted on this load. |

### Revision numbers and PDF inventory (after test)

| # | Role | Filename | SHA-256 | Storage key (suffix) |
|---|------|----------|---------|----------------------|
| — | **Original** RC | `Armstrong.pdf` | `1c827d7d2bf59ea86c738af56d260cb5372cf1f4b2deb1b47528d6737273f0f4` | `…/8e53374eeb2c474eb5178952f6a71210.pdf` |
| 1 | Revised | `Armstrong_TEST_rate_2000.pdf` | `73552d5ef08ecce371b03015f1afd50c3e076b9331c2246fa4138d16dcc6ca6e` | `…/f5b3744263864dcfa9f76a0e1122559b.pdf` |
| 2 | Revised | `Armstrong_TEST_rate_2000.pdf` | `73552d5e…` (same bytes as rev 1; pre-B1 duplicate pointers) | `…/0f1794ab492b41a3905960c45553e82b.pdf` |
| 3 | **New B1 attach** | `Armstrong_B1_revision3_test.pdf` | `d9d6436a3d96a61da2d6d8f7222a40da0c79b6e604f307c7b461b92c1d3e51c0` | `…/8717a1130b6b4a37886a2f6c94cba52e.pdf` |

**Storage backend:** `local` (from export and API).

### Download / read-back verification

All via **`GET /api/v1/loads/1010/rate-confirmation-pdf`** (original) and **`?revision=1|2|3`** (Billing uses the same commercial RC download route).

| GET | HTTP | Downloaded SHA matches |
|-----|------|-------------------------|
| Original | 200 | `1c827d7d…` = DB `file_sha256` |
| `?revision=1` | 200 | `73552d5e…` |
| `?revision=2` | 200 | `73552d5e…` |
| `?revision=3` | 200 | `d9d6436a…` = uploaded fixture |

Header **`X-Revised-Rate-Confirmations`:** `3` before and after duplicate reattach.

### Database snapshots (complete load + stops + verified JSON)

| Label | Path |
|--------|------|
| Before third attach | `docs/reports/milestone_b1_evidence/load_1010_before_third_revision.json` |
| After third attach + dedupe reattach | `docs/reports/milestone_b1_evidence/load_1010_after_third_revision.json` |

**Before → after comparison (automated diff):**

- `loads_row`: no change on commercial fields (`rate` 2100.00, `customer_rate` 1999.00, `broker_load_reference`, stops-related snapshots, etc.); only `updated_at` / `concurrency_version` may drift on unrelated saves — **not** modified by attach in this test window.
- `load_stops`: **identical** (2 stops).
- `accepted_parse_json.extracted`: **identical** (business values unchanged).
- `_revised_pdfs`: **2 → 3** pointers; rev 3 includes `uploaded_at` `2026-10-30T07:03:27.335219+00:00`.

### Logs

**Application (truckerp-api, excerpt):**

```
POST /api/v1/loads/1010/rate-confirmation-revised-attachment HTTP/1.0" 200 OK
GET  /api/v1/loads/1010/rate-confirmation-pdf HTTP/1.0" 200 OK
GET  /api/v1/loads/1010/rate-confirmation-pdf?revision=1 HTTP/1.0" 200 OK
GET  /api/v1/loads/1010/rate-confirmation-pdf?revision=2 HTTP/1.0" 200 OK
GET  /api/v1/loads/1010/rate-confirmation-pdf?revision=3 HTTP/1.0" 200 OK
POST /api/v1/loads/1010/rate-confirmation-revised-attachment HTTP/1.0" 200 OK  (duplicate)
```

**Audit (`audit_events`, tenant 53, entity load 1010):**

| action | revision_index (context) | pdf_sha256 (prefix) | created_at |
|--------|--------------------------|---------------------|------------|
| `load_revised_rc_attached` | 3 | `d9d6436a…` | 2026-10-30 07:03:27 UTC |

### Failures / discrepancies

- **None** for the third-revision browser test.
- **Note:** Revisions 1 and 2 are duplicate byte content from pre-B1 experiments (two storage keys, one SHA). B1 dedupe prevents a **third** copy of the same SHA; the B1 test used **new bytes** for revision 3.

---

## Implementation summary

### Backend

- `attach_revised_rate_confirmation_pdf` in `app/services/loads.py`
- `POST /api/v1/loads/{load_id}/rate-confirmation-revised-attachment`
- Schema `LoadRevisedRateConfirmationAttachmentResponse`; authz in `app/authz/routes.py`

### Frontend

- `attachRevisedRateConfirmation` in `apps/web/src/api.ts`
- **Attach revised PDF** on `LoadWorkspacePage.tsx` (file chooser via button; success toolbar message)

### Tests / tooling

- `tests/test_revised_rc_attach.py` — **2 passed**
- `tests/e2e/milestone_b1_attach.spec.ts` — dedupe / $2k fixture
- `tests/e2e/milestone_b1_attach_third_revision.spec.ts` — **new revision (required)**
- `scripts/b1_load_evidence_export.py` — load row, stops, evidence, PDF read-back hashes

### Unchanged (B1 gates)

- First parser, AI compare, Re-parse UI
- `app/core/storage.py`, `app/routers/driver_onboarding.py` — **not** in B1 commit

---

## Deployment verification (playground)

| Surface | Evidence |
|---------|----------|
| API | `POST …/rate-confirmation-revised-attachment` in running `truckerp-api` image |
| Frontend | nginx bundle includes **Attach revised PDF** (e.g. `index-CW139VKe.js` after rebuild) |

---

## Requirements checklist

| # | Requirement | Result |
|---|-------------|--------|
| 1 | Preserve original and prior revisions | **PASS** |
| 2 | Attach independent of Load-field save | **PASS** |
| 3 | No duplicate storage for identical bytes | **PASS** (duplicate POST `stored_new: false`) |
| 4 | Filename, SHA-256, storage key, timestamp | **PASS** (rev 3 pointer) |
| 5 | Dispatch + Billing download paths | **PASS** (`rate-confirmation-pdf` + `revision`) |
| 6 | Tenant isolation / auth / audit | **PASS** |
| 7 | No verified JSON business mutation on attach | **PASS** |
| 8 | Existing storage | **PASS** (`local`) |
| 9 | No parser/compare changes | **PASS** |
| 10 | No unrelated module changes in commit | **PASS** (see commit file list) |

---

## STOP

B1 verification complete. Do **not** start B2 (optional parse, per-field Use, retire AI compare) until owner accepts this report.
