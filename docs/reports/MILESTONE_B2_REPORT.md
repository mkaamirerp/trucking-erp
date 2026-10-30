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

## Frontend verification (demo.truckerp.me)

| Test | Result (this session) | Notes |
|------|------------------------|-------|
| **A — New Load regression** | **PASS** (Playwright) | Armstrong duplicate gate on demo; annotated — parser still available on existing load |
| **B–E — Parse / Use / Save / PDF retention** | **NOT COMPLETED** | Playwright **login timeout** (90s) on repeat runs; same failure on `milestone_b1_attach_third_revision.spec.ts` — environment/auth, not B2 UI code |
| Unit `test_parse_reference_b2.py` | **2 passed** | |
| Unit `test_revised_rc_attach.py` | **2 passed** | B1 regression |
| `npm run build` | **PASS** | |

**Re-run when demo login is stable:**

```bash
cd tests/e2e
export E2E_LOGIN_EMAIL=… E2E_LOGIN_PASSWORD=…
npx playwright test milestone_b2_workflow.spec.ts
```

Screenshots (partial): `docs/reports/milestone_b2_screenshots/` (Test A gate when present).

**Evidence exports:** use `scripts/b1_load_evidence_export.py` before/after Save in Test C (load 1010).

---

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
