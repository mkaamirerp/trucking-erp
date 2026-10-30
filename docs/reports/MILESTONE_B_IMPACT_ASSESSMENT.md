# Milestone B — Impact assessment (simplified Re-parse / revised PDF)

**Status:** Pre-implementation boundary document. **No Milestone B code in this file.**  
**Branch baseline:** `gpt-review` @ `caa95a8` (post Milestone A cleanup).  
**Authority:** Owner Milestone B spec (2026-10-30); `.cursor/rules/owner-product-rules.mdc` RE-PARSE section **must be updated after** Phase 2 is verified (not during cleanup).

---

## Architectural target (one line)

**New Load:** Parse → Review → Create.  
**Existing Load:** Edit → Save.  
**Revised RC:** Attach PDF (no field writes) → optional Parse (first parser only) → dispatcher copies values manually → Save Load reconciles JSON.  
**Billing:** Original + numbered revised PDFs via existing download routes.

---

## 1. Existing frontend components to reuse

| Component / module | Path | Reuse |
|--------------------|------|--------|
| Load form + save | `apps/web/src/pages/LoadWorkspacePage.tsx`, `LoadWorkspaceForm.tsx` | **Keep** as sole writer of load fields; ordinary **Save load** stays the only persist path for business fields. |
| Parse hydration (New Load) | `applyLoadDocumentParseResponse.ts`, `loadParseHydrationState.ts` | **Do not** call on existing-load Parse for auto-hydrate. **Do** reuse field mapping / display helpers when building a **read-only “extracted values” panel** (labels, money, stops formatting). |
| RC PDF panel | `RateConfirmationPdfPanel.tsx` | **Keep** — already lists `revisedPdfPaths` with `?revision=N` download links. Extend labels (“Revised RC 1”, …). |
| Duplicate PDF gate (new load) | `DuplicateLoadParseGateDialog.tsx` | **Unchanged** for New Load; not in Milestone B scope. |
| API client | `apps/web/src/api.ts` | **Extend** with attach-only + parse-reference endpoints; **retire** `saveLoadReparse` combined save once backend split exists. |
| Integration tests (unit) | `loadWorkspaceParsePersist.integration.test.ts` | **Update** scenarios that assume re-parse popup + combined save; patterns for reconcile-on-save remain valid. |

**Replace / retire (UI):**

| Component | Path | Why |
|-----------|------|-----|
| Comparison popup | `ReparseChangesDialog.tsx` | Built for AI **difference rows**, Use new value, acknowledgement for wrong file. |
| Re-parse state machine | `LoadWorkspacePage.tsx` (`reparseProposal`, `reparseFile`, integrity, `saveLoadReparse`) | Couples upload + compare + PDF store + form save in one flow. |

**New UI (minimal):**

- **Attach Revised PDF** — file input + POST attach endpoint; success toast; refresh `revisedPdfPaths` from GET load / revised count header.
- **Parse PDF** — enabled when a **pending or latest attached** revised file exists (or user selects file → attach first, or parse uploaded bytes without storing — owner spec prefers attach then parse; **attach-first** matches billing).
- **Parse reference panel** — side-by-side or table: **Saved load** vs **Extracted from PDF** (from `LoadDocumentParseResponse.extracted`); **no** Apply-all; optional “Copy to form” per field or manual edit only (smallest: **no** one-click apply in v1 if it risks second mapping engine — manual copy satisfies spec).

---

## 2. Existing attachment and PDF-history code to reuse

| Capability | Location | Notes |
|------------|----------|--------|
| Original RC storage | `load_commercial_evidence` + `read_load_rate_confirmation_pdf_bytes` | **Unchanged** — original `storage_key` / `file_sha256` never overwritten. |
| Revised history in verified JSON | `load_workspace_draft_document.py`: `_revised_pdfs`, `revised_pdf_records`, `append_revised_pdf` | **Primary history mechanism today** (pointers: `storage_key`, `sha256`, `filename`). |
| Store revised bytes | `loads.py` `update_load` → `_persist_verified_parse_and_optional_revised_pdf` (via `revised_pdf_bytes`) | **Reuse** storage module `store_load_commercial_pdf` pattern already used for `load_revised_rc`. |
| Duplicate-byte detection | `classify_load_pdf_reuse`, `known_pdf_reuse_message` | **Reuse** for attach: skip append when status is `existing_original` / `existing_latest_revision` / prior revision (Scenario E). |
| Download / Billing read | `GET /loads/{id}/rate-confirmation-pdf`, `?revision=N` | **Reuse** — no new billing API required for MVP if billing uses same authenticated download URLs. |
| Document block (non-RC) | `reparse_document_block_reason` | **Reuse** on attach/parse upload — reject fuel invoice, etc. |
| Cross-load duplicate PDF | `find_exact_pdf_duplicate_candidates` | **Reuse** on attach/parse — 409 if PDF belongs to another load. |

**Not present in current tree (commit log mentioned `rc01_*` / snapshot models):** no separate `load_rate_confirmation_revision` **table** in workspace; history is **JSON pointers + storage keys**. **No new migration required** for Milestone B MVP unless owner wants DB-normalized revision rows later.

**S3:** `settings.storage_provider` defaults **`local`** on playground; S3 bucket configured in `app/core/config.py`. **Verify-only:** document current provider per tenant/host; **no** provider switch or migration in Milestone B.

---

## 3. Minimum backend changes (smallest focused set)

Ordered for incremental delivery:

### Step B1 — Attach-only API (no AI, no load field writes)

- **New route:** e.g. `POST /api/v1/loads/{load_id}/rate-confirmation-revised-attachment` (name TBD, RBAC same as load update).
- **Behavior:** Read PDF → `_read_reparse_pdf` validation → `classify_load_pdf_reuse` → if `new_revision`, store via existing storage helper + `append_revised_pdf` on `accepted_parse_json` **without** `reconcile_accepted_parse_json` from form changes → commit evidence row only (load columns untouched).
- **Idempotency:** If not `new_revision`, return **200** with `already_on_load: true` and **no** new storage object (Scenario E).
- **Metadata:** Extend pointer dict with `uploaded_at` (UTC ISO) if not already present (additive JSON, no migration).

### Step B2 — Parse-reference API (first parser only)

- **Replace or narrow** `POST …/rate-confirmation-reparse`: remove `load_reparse_changes` compare call (`_COMPARE_*`, `validate_ai_reparse_changes` for proposal).
- **New response model:** e.g. `LoadParseReferenceResponse` = `{ parse: LoadDocumentParseResponse, pdf_reuse_status, document_warnings? }` — **no** `changes`, **no** `integrity` token tied to compare baseline (optional short-lived session id if needed for UX only).
- **Implementation:** Reuse **`parse_load_workspace_document_orchestrated`** exactly as today (same model, prompts, schema). Keep **identity / block** checks that protect tenant (`reparse_document_block_reason`, cross-load duplicate) but **drop** `assess_same_load` gating that exists only to drive comparison popup — or reduce to **warnings** in response without blocking parse read (owner: parse is reference only).

### Step B3 — Retire combined re-parse save

- **Deprecate** `POST …/rate-confirmation-reparse/save` (or make it attach-only shim temporarily).
- **Existing Load field + JSON updates:** only **`PATCH/PUT` load update** path already calling `reconcile_accepted_parse_json(accepted, form)` on save — **no** `verified_parse=revised_parse` from parser output unless dispatcher edited form (today’s bug class: reparse save replacing JSON from parser — **remove**).

### Step B4 — Authz + schemas

- Update `app/authz/routes.py` bindings for new attach route; mark old reparse save as deprecated or remove after UI cutover.
- Trim `LoadReparseProposal` / `LoadReparseChange` from public API when unused (keep internal test helpers until tests migrated).

**Files touched (expected, not exhaustive):**

- `app/routers/loads.py` — routes
- `app/services/load_document_parse_orchestrator.py` — delete compare stage; add `parse_load_rate_confirmation_reference` (name TBD)
- `app/services/loads.py` — small helper `attach_revised_rate_confirmation_pdf(...)` extracting logic from `update_load` revised branch
- `app/schemas/load_document_parse.py` — new response type
- `apps/web/src/pages/LoadWorkspacePage.tsx` — three actions UX
- `apps/web/src/api.ts` — client methods
- **Delete or gut:** compare-specific portions of `load_workspace_draft_document.py` (`validate_ai_reparse_changes`, `_supported_reparse_differences` for AI popup) — **after** tests rewritten; some **deterministic** diff helpers may remain for unit tests or future reference UI

---

## 4. Old AI comparison components that become unnecessary

| Piece | Location | Action |
|-------|----------|--------|
| JSON1/JSON2 compare prompt | `load_document_parse_orchestrator.py` `_COMPARE_INSTRUCTIONS`, `_COMPARE_SCHEMA` | **Remove** from active path |
| Second AI call `load_reparse_changes` | same + `load_document_parse_semantic_llm` | **Remove** |
| `validate_ai_reparse_changes` / AI row grounding for popup | `load_workspace_draft_document.py` | **Remove** from proposal path (large function graph) |
| `LoadReparseProposal.changes` | schema + frontend dialog | **Remove** |
| `reparse_integrity_token` / signed proposal for compare+save | orchestrator + `update_load` reparse gate | **Remove** or restrict to legacy until save endpoint gone |
| `saveLoadReparse` + form `reparseSavedFormOnly` paths | frontend | **Remove** |
| Milestone A experiment | already removed | — |

**Keep (still needed):**

- `parse_load_workspace_document_orchestrated` / first parser pipeline
- `reconcile_accepted_parse_json` on normal save
- `append_revised_pdf` / download readers
- `classify_load_pdf_reuse`

---

## 5. Database migration and billing integration

| Question | Assessment |
|----------|------------|
| **New tables?** | **Not required** for MVP if continuing `_revised_pdfs` in `accepted_parse_json`. |
| **Alembic** | **Preserve** all existing migration files; **do not roll back**. |
| **Billing module** | **No code change required** if billing already uses load PDF download URLs or load detail; confirm consumers in separate grep before release. |
| **Metadata** | Optional additive fields on revision pointers (`uploaded_at`, `uploaded_by`) — JSON only. |
| **S3 migration** | **Separate approval** — document `storage_provider` at deploy time only. |

---

## 6. Potential regressions

| Risk | Mitigation |
|------|------------|
| **First parser** | Touch orchestrator only **after** parse path extracted; run `tests/test_load_document_parse_*`, New Load Playwright, parser smoke on **non-duplicate** PDF. |
| **Ordinary edit/save** | Keep `update_load` reconcile path unchanged; add tests: edit rate/address → save → JSON matches form. |
| **Customer rate hydration** | Do not call `applyLoadDocumentParseResponse` on existing load parse. |
| **Original PDF** | Attach path must **never** mutate `load_commercial_evidence.storage_key` / original sha. |
| **Duplicate attachments** | Must call `classify_load_pdf_reuse` on attach; unit tests from Scenario E. |
| **`tests/test_reparse_replacement.py`** | Large suite asserts AI comparison — **rewrite** to attach + parse-reference + save reconcile; expect many deletions, not a silent skip. |
| **Owner rules doc** | RE-PARSE section still describes old popup — update **after** frontend verification (owner instruction). |
| **Demo load 1010** | Messy experiment state — use fresh load for Scenario A acceptance or document baseline. |

---

## 7. Suggested implementation checkpoints (smallest path)

| Checkpoint | Deliverable | Frontend proof |
|------------|-------------|----------------|
| **B1** | Attach-only API + UI button | Scenario C partial: attach 2k PDF, downloads, load fields unchanged |
| **B2** | Parse-reference API + read-only panel | Scenario D: parse revised, load unchanged |
| **B3** | Remove compare popup + combined save | Scenario B + D save after manual edit |
| **B4** | Tests + Playwright scenarios A–E | Evidence package per owner §9 |

**Do not** merge checkpoints without owner review per `gpt-review-gates.mdc`.

---

## 8. Acceptance verification plan (§9 mapping)

| Scenario | Primary evidence |
|----------|------------------|
| A New Load | Playwright + DB export read-only: load row, stops, `accepted_parse_json`, original PDF sha |
| B Manual edit | Before/after snapshots, reconcile array |
| C Attach | Two PDFs downloadable; load row diff empty for rate/stops |
| D Optional parse | Parse response JSON artifact; load row unchanged until Save |
| E Repeat attach | Second attach same bytes → no new `_revised_pdfs` entry |

Use **`tests/e2e/parser_regression_minimal.spec.ts`** as seed; extend into `milestone_b_acceptance.spec.ts` after B1–B3 (no 18-test matrix).

---

## 9. STOP / owner confirmation before coding

Confirm:

1. **Attach endpoint** naming and whether **parse** requires prior attach or may accept ephemeral upload.
2. **Parse reference UI:** manual-only field transfer vs per-field “Use extracted value” (still explicit click, reusing one mapping function).
3. **Warnings vs hard-stop** on `assess_same_load` mismatch when parse is reference-only.

**After confirmation:** implement **B1 only**, deploy to dev playground with owner approval, then report evidence before B2.

---

## 10. Summary table (owner questions 1–6)

| # | Answer |
|---|--------|
| 1 Frontend reuse | Load workspace form/save, RC panel, parse display helpers; replace ReparseChangesDialog + reparse save state |
| 2 Attachment reuse | `_revised_pdfs`, `append_revised_pdf`, storage store, `classify_load_pdf_reuse`, GET PDF with `revision` |
| 3 Min backend | Attach route; parse-reference route; remove compare AI + combined save; reconcile only on normal save |
| 4 Obsolete | Compare prompt/schema, `load_reparse_changes`, validate AI popup pipeline, integrity+save reparse endpoint |
| 5 Migrations | **None** for MVP; billing likely **no change**; S3 verify separately |
| 6 Regressions | First parser, reconcile save, customer rate, duplicate attach, large reparse test suite |

**No broad rewrite.** Refactor committed re-parse paths in place; preserve migrations and storage abstraction.
