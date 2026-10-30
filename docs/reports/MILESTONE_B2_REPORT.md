# Milestone B2 — Simplified Parse PDF (Existing Load)

**Status:** Implemented on `gpt-review` (commit pending push). **STOP before merge to `main`.** No production deploy beyond dev playground API/nginx rebuild.

**Baseline:** B1 @ `e30a37a`.

---

## Summary

Replaced the AI JSON1/JSON2 **Re-parse** workflow with:

**Attach revised PDF (B1) → optional Parse PDF (first parser only) → per-field “Use extracted value” (form only) → Save load.**

- **New Load path unchanged** (same upload → first parser → review → create).
- **No second parser, no compare AI, no `saveLoadReparse`, no `ReparseChangesDialog`.**
- **Billing PDF routes unchanged** (`GET …/rate-confirmation-pdf` + `?revision=N`).

---

## Changed files and purpose

| Path | Purpose |
|------|---------|
| `app/services/load_document_parse_orchestrator.py` | Removed compare prompt/schema and `propose_load_reparse`; added `parse_attached_rate_confirmation_reference` |
| `app/services/load_workspace_draft_document.py` | Added `build_parse_reference_field_rows` (deterministic diff rows) |
| `app/schemas/load_document_parse.py` | Added `LoadParseReferenceResponse`; removed `LoadReparseProposal` |
| `app/routers/loads.py` | `POST …/rate-confirmation-parse-reference`; removed reparse + reparse/save |
| `app/services/loads.py` | Removed reparse integrity / `verified_parse` save path from `update_load` |
| `app/authz/routes.py` | Authz for parse-reference route |
| `apps/web/src/api.ts` | `parseLoadRateConfirmationReference`; removed reparse/save client |
| `apps/web/src/pages/LoadWorkspacePage.tsx` | Parse PDF UI, review panel, normal Save only |
| `apps/web/src/loadWorkspace/ParseReferenceReviewDialog.tsx` | **New** review table |
| `apps/web/src/loadWorkspace/parseReferenceFormMerge.ts` | **New** merge form into row “current load” column |
| `apps/web/src/loadWorkspace/ReparseChangesDialog.tsx` | **Deleted** |
| `tests/test_parse_reference_b2.py` | **New** unit tests |
| `tests/test_reparse_replacement.py` | Skipped (legacy compare suite) |
| `tests/e2e/milestone_b2_workflow.spec.ts` | **New** focused demo tests A–E |

---

## Backend API

**`POST /api/v1/loads/{load_id}/rate-confirmation-parse-reference`**

- Form field: `revision` (≥ 1) — reads attached revised PDF bytes from storage.
- Runs **`parse_load_workspace_document_orchestrated`** (same as New Load).
- Returns `LoadParseReferenceResponse`: `parse`, deterministic `field_rows`, optional identity `warnings`.
- **No DB writes.**

Removed:

- `POST …/rate-confirmation-reparse`
- `POST …/rate-confirmation-reparse/save`

---

## Frontend verification (demo.truckerp.me) — **PASS** (2026-10-30)

**Harness:** `tests/e2e/global-setup.ts` — **one login per run** (or reuse `.auth/demo-user.json` if &lt; 1h old). Tests use `storageState`; no per-test login (avoids HTTP **429** lockout).

**Spec:** `tests/e2e/milestone_b2_frontend_verification.spec.ts` (serial, 4 tests) — **4 passed (~54s)**.

| # | Test | Result |
|---|------|--------|
| 1 | Parse PDF — extraction panel; **form unchanged** | **PASS** |
| 2 | **Use extracted rate** only → Save → reload matches | **PASS** |
| 3 | Parse again → **Close** without Use → form unchanged | **PASS** |
| 4 | Original + all revised PDFs download (SHA read-back) | **PASS** |

**Load under test:** demo tenant load **`1011`** (`Oct-26-0338`) — load **1010** no longer exists on `tenant_demo` (empty DB at start of session); `beforeAll` seeded Armstrong create + attached valid **`Armstrong_TEST_rate_2000.pdf`** revised RC.

**Screenshots:** `docs/reports/milestone_b2_screenshots/verify-01` … `verify-06`  
**Evidence:** `docs/reports/milestone_b2_evidence/active_load_id.txt`, `load_1011_after_b2_frontend_verify.json`, `pdf_download_verification.json`

**Note:** B1 test fixture `Armstrong_B1_revision3_test.pdf` (PDF comment append) is **not parser-safe** (`PdfReadError`); parse-reference correctly requires a valid RC PDF. Use archive **`Armstrong_TEST_rate_2000.pdf`** for parse E2E.

### Earlier failures (explained)

| Symptom | Cause |
|---------|--------|
| Login timeout | **429** rate limit from repeated per-test logins — fixed by `global-setup` + `storageState` |
| PDF viewer timeout on 1010 | **`tenant_demo` had zero loads** — 1010 removed/empty DB |
| Parse-reference **500** | Attached **malformed** revised PDF (B1 byte-append fixture) — use valid PDF |
| Create-load `waitForURL` | Load **1011** created but UI navigated to **dashboard** before URL assert — fixed by polling API |

## Deployment verification (playground)

- API image rebuilt; route present: `rate-confirmation-parse-reference`
- Nginx rebuilt; bundle includes **Parse PDF** and parse-reference dialog strings

---

## Known limitations

- Parse reference **field_rows** diff uses verified JSON vs new parse; UI **overlays current form** values in the “Current load” column via `mergeParseReferenceRowsWithForm`.
- Identity **hard-block** still uses `assess_same_load` for reliable mismatch; soft issues return **warnings** only.
- Demo **duplicate Armstrong** on New Load prevents full Test A create path without a fresh PDF tenant.

---

## STOP

B2 implementation complete in repo. **Do not merge to `main`** until owner accepts report and frontend Tests B–E are re-run with successful login.
