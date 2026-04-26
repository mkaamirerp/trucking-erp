# Load Lab Cleaner — rollout cleanup ledger

## Purpose

This file is the **cleanup ledger** for Load Lab rollout work.

- Every **temporary shortcut**, **copied or forked UI**, **bridge path**, **debug-only behavior**, **duplicate route**, or **transitional persistence** choice must be logged here.
- **Update this file in the same change pass** as any temporary measure — do not defer documentation.

Related design docs: `docs/LOAD_LAB_FIRST_MIGRATION_CUT.md`, `docs/LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`, `docs/LOAD_LAB_WORKSPACE_PARITY_NOTE.md`, `docs/PDF_LOAD_PIPELINE.md`, `docs/OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`.

---

## How to add an entry

Use the structure below for each item. **Status** must be one of: `open` | `deferred` | `done`.

### Entry template (copy below)

- **Title:** (H3 heading in the ledger)
- **Type:** `route` | `UI copy` | `API bridge` | `parser bridge` | `temp table` | `debug log` | `feature flag` | `other`
- **Location(s):** `path` or `path:line`
- **Why it was introduced:**
- **Why it is temporary:**
- **Risk if left behind:**
- **Cleanup target:**
- **Removal trigger / when safe to clean:**
- **Status:** `open` | `deferred` | `done`

---

## Ledger entries

### Load Lab v1 shares regex PDF parser with workspace parse

- **Type:** parser bridge
- **Location(s):** `app/services/load_lab.py` (`parse_load_workspace_from_pdf_bytes` from `app/services/load_document_parse.py`); compare `POST /api/v1/loads/parse-document` in `app/routers/loads.py`
- **Why it was introduced:** Ship persisted runs, UI, and promote flow without waiting on OpenAI/OCR pipeline.
- **Why it is temporary:** Design intent is OpenAI (schema-driven) as primary semantic layer; regex is interim acquisition/mapping for Lab only until that lands.
- **Risk if left behind:** Two product surfaces (Load workspace vs Lab) drift in behavior; operators confuse “Lab parse” with “final pipeline”; version pins (`PARSER_VERSION`, etc.) may not reflect true semantic engine.
- **Cleanup target:** Single documented mapping path for Lab: normalized package → OpenAI (or equivalent) → validation; regex optional pre-pass or fallback only, with explicit version fields.
- **Removal trigger / when safe to clean:** OpenAI mapping is production-ready in Lab, tested on representative PDFs, and `parser_version` / `model_name` reflect the new stack; regression plan signed off.
- **Status:** open

---

### Image-only / weak-text PDFs: OCR not implemented — runs end `failed` or `ocr_required` + `failed`

- **Type:** parser bridge
- **Location(s):** `app/services/load_lab.py` (`ingest_pdf_and_run_pipeline` — no text branch)
- **Why it was introduced:** Readability gate exists in design; Textract/OCR not wired in v1.
- **Why it is temporary:** `docs/PDF_LOAD_PIPELINE.md` requires OCR acquisition branch feeding the same normalized contract.
- **Risk if left behind:** Operators assume Lab “handles all PDFs”; support burden; false sense of completeness.
- **Cleanup target:** Implement OCR branch, set `ocr_engine_version`, transition statuses (`ocr_required` → `ocr_complete`) per design doc; adjust failure/review rules.
- **Removal trigger / when safe to clean:** OCR path merged, tenant-configurable or always-on for Lab, smoke-tested on scanned samples.
- **Status:** open

---

### Promote API: `apply_all=false` rejected (not implemented)

- **Type:** API bridge
- **Location(s):** `app/services/load_lab.py` (`promote_run`); `app/schemas/load_lab.py` (`LoadLabPromoteBody`); `apps/web/src/pages/LoadLabPage.tsx` (always full apply)
- **Why it was introduced:** Fastest safe promote: map full extracted payload to `LoadCreate` / `LoadUpdate` without field-level UI contract.
- **Why it is temporary:** Design calls for explicit fields accepted/blocked and overwrite decisions on promote; promote audit shape already allows lists/objects.
- **Risk if left behind:** Promote overwrites large slices of a load without per-field consent; weaker alignment with `LOAD_LAB` promote audit intent.
- **Cleanup target:** Field-level (or group-level) accept list in API + UI; persist `fields_accepted` / `fields_blocked` accurately in `load_lab_promote_audits`.
- **Removal trigger / when safe to clean:** UI + backend support granular selection and tests cover partial promote + blocked fields.
- **Status:** open

---

### Reject run stores operator note in `pipeline_error`

- **Type:** transitional persistence
- **Location(s):** `app/services/load_lab.py` (`reject_run` — sets `run.pipeline_error = note`)
- **Why it was introduced:** No dedicated `reject_note` column in v1 migration; reuse existing nullable text field.
- **Risk if left behind:** UI/metrics confuse pipeline failures with human reject reasons; reporting queries unreliable.
- **Cleanup target:** Add `reject_note` or `operator_reject_reason` (or store only in `audit_events.context_json` and clear `pipeline_error` on reject).
- **Removal trigger / when safe to clean:** After Alembic tenant migration + backfill/migration script if needed; UI updated to read the new field.
- **Status:** open

---

### `audit_events` for Load Lab uses `actor_label` (`platform:{uuid}`) not `actor_user_id`

- **Type:** other (audit workaround)
- **Location(s):** `app/services/load_lab.py` (`reject_run`, `promote_run` — `write_audit_event`); `app/services/audit_events.py` (`actor_user_id` is `BigInteger`, platform users are UUID strings)
- **Why it was introduced:** Append-only audit table expects numeric `actor_user_id`; current user is platform UUID string from JWT.
- **Why it is temporary:** Long-term may map platform user → tenant user row id for joins, or extend audit contract for string actors (product/DB decision).
- **Risk if left behind:** Harder to correlate Lab audits with people directory; inconsistent with other modules that pass numeric ids.
- **Cleanup target:** Documented actor model for tenant-scoped actions; optional FK or stable `actor_platform_user_id` column on audit payload only (not necessarily schema change if `context_json` suffices).
- **Removal trigger / when safe to clean:** After RBAC/identity decision and any one-off migration for reporting.
- **Status:** deferred

---

### Load Lab UI: local `JsonBlock` and bespoke layout (not shared with Load workspace)

- **Type:** UI copy / other
- **Location(s):** `apps/web/src/pages/LoadLabPage.tsx` (`JsonBlock`, page layout)
- **Why it was introduced:** Ship review surface quickly without extracting shared “JSON panel” or workspace subcomponents.
- **Risk if left behind:** Style/behavior drift from `LoadWorkspacePage` / intake panels; duplicated accessibility fixes.
- **Cleanup target:** Shared presentational components or design-system panel for “readonly JSON + copy button” used by Lab and diagnostics.
- **Removal trigger / when safe to clean:** Second consumer page needs the same pattern, or design pass for ops tools.
- **Status:** open

---

### Version pins `n/a-regex-only` for `MODEL_NAME` / `PROMPT_VERSION`

- **Type:** other
- **Location(s):** `app/services/load_lab.py` (constants `MODEL_NAME`, `PROMPT_VERSION`)
- **Why it was introduced:** Satisfy non-null versioning columns before OpenAI exists.
- **Why it is temporary:** Real runs should record actual model id and prompt bundle version per `LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`.
- **Risk if left behind:** Analytics and dedupe reuse logic treat regex and OpenAI runs as the same “version” if strings collide.
- **Cleanup target:** Distinct sentinel vs absent; or allow null for pre-AI era rows only with migration; set real values when OpenAI ships.
- **Removal trigger / when safe to clean:** First OpenAI-backed deploy; document sentinel values in runbook if retained for historical rows.
- **Status:** open

---

### Duplicate HTTP entry points to same regex parser (workspace vs Lab)

- **Type:** API bridge
- **Location(s):** `POST /api/v1/loads/parse-document` vs `POST /api/v1/load-lab/runs/upload` (both ultimately `parse_load_workspace_from_pdf_bytes` for text path)
- **Why it was introduced:** Workspace must stay backward-compatible; Lab adds persistence and audit.
- **Why it is temporary:** Not duplicate logic forever — workspace might call “internal parse + optional suggest” or Lab becomes sole experimental surface.
- **Risk if left behind:** Security/rate-limit divergence (one path audited, one not); inconsistent max size or validation.
- **Cleanup target:** Single internal service function for “bytes → parse dict” with shared limits; routes differ only in persistence and auth.
- **Removal trigger / when safe to clean:** Security review or when workspace parse is deprecated in favor of Lab-backed suggestions.
- **Status:** open

---

### OpenAI connectivity smoke (admin HTTP + CLI)

- **Type:** other
- **Location(s):** `app/routers/load_lab.py` — `POST /openai-smoke`; `app/scripts/openai_smoke.py`; `app/core/config.py` — `openai_api_key`; `apps/web/src/pages/LoadLabPage.tsx` (admin button); `apps/web/src/api.ts` — `postLoadLabOpenaiSmoke`
- **Why it was introduced:** Verify `OPENAI_API_KEY` and outbound access before building semantic mapping; no PDF parsing side effects.
- **Why it is temporary:** Route location may move to a global ops/diagnostics module once RBAC is finalized; probe may switch to a lighter API if OpenAI deprecates `GET /v1/models` listing for keys.
- **Risk if left behind:** Admins spamming smoke → rate limits; **mitigation:** tenant-admin gate only; do not add to health checks.
- **Cleanup target:** Consolidate with platform diagnostics or scripted-only ops if HTTP surface is unwanted long-term.
- **Removal trigger / when safe to clean:** Product decides all OpenAI checks are CI-only or a different admin surface owns them.
- **Status:** open

---

### Load Lab v1 uses private `_extract_text_from_pdf_bytes` helper (import from `load_document_parse.py`)

- **Type:** parser bridge
- **Location(s):** `app/services/load_lab.py` imports `_extract_text_from_pdf_bytes` from `app/services/load_document_parse.py`
- **Why it was introduced:** Smallest v1 slice needs local text extraction without adding a new PDF parsing dependency or rewriting existing logic.
- **Why it is temporary:** Leading-underscore helper is a private implementation detail of the workspace parser module; long-term extraction should live in a shared “text acquisition” module used by both workspace and Lab (and eventually OCR).
- **Risk if left behind:** Refactors in `load_document_parse.py` can silently break Lab; unclear ownership of “acquisition” vs “semantic extraction” stages.
- **Cleanup target:** Move the text acquisition primitive into a dedicated module (e.g. `app/services/pdf_text_acquire.py`) with a stable API and tests; update both workspace parse and Lab to import from it.
- **Removal trigger / when safe to clean:** When the next pipeline slice adds OCR acquisition or introduces a canonical normalized package builder shared across entry points.
- **Status:** open

---

### Load Lab “promote/reject” endpoints removed for v1 slice lock

- **Type:** route
- **Location(s):** Removed from `app/routers/load_lab.py`; removed UI actions from `apps/web/src/pages/LoadLabPage.tsx`; removed API helpers from `apps/web/src/api.ts`
- **Why it was introduced:** Align running code with the accepted “v1 slice only” scope: no operational load writes, no promote, no candidate JSON mapping.
- **Why it is temporary:** Promote and explicit operator actions are part of the larger Load Lab design, but were intentionally deferred for this cut.
- **Risk if left behind:** Lab becomes “view-only” forever; operators may request promote back earlier than planned.
- **Cleanup target:** Reintroduce promote/reject only when semantic mapping + validation gates are ready and per-field accept/block rules are defined.
- **Removal trigger / when safe to clean:** After OpenAI mapping (or other semantic layer) is producing canonical candidate JSON and deterministic validation + contradiction gates are in place.
- **Status:** open

---

### Load Lab v2 semantic extract: httpx + `json_schema` with `json_object` fallback (no `openai` SDK)

- **Type:** API bridge
- **Location(s):** `app/services/load_lab_semantic.py` (`_openai_chat_json_schema` → `https://api.openai.com/v1/chat/completions`)
- **Why it was introduced:** Reuse the existing `httpx` dependency and the same auth pattern as `POST /load-lab/openai-smoke`; avoid adding another client stack until SDK features are required.
- **Why it is temporary:** Structured-output ergonomics (streaming, retries, typed `parse`, Assistants) are better handled by the official SDK or a thin shared client module once Load Lab needs more than one OpenAI call shape.
- **Risk if left behind:** Manual JSON handling drifts from OpenAI API changes; schema submission quirks (`$defs`, strict mode) are handled only empirically.
- **Cleanup target:** Optional `openai` package + one shared async client helper used by smoke + semantic extract; centralize model IDs and timeouts.
- **Removal trigger / when safe to clean:** When a second OpenAI-backed feature ships or retries/rate-limit handling becomes non-trivial.
- **Status:** open

---

### Load Lab upload: digital branch auto-runs semantic mapping to persist `parse_response`

- **Type:** API bridge
- **Location(s):** `app/services/load_lab.py` (`ingest_pdf_and_run_pipeline` now invokes `load_lab_semantic.semantic_extract_run` after `status="text_extracted"` commit)
- **Why it was introduced:** Lock the intended pipeline order: upload should return canonical candidate JSON for digital PDFs without requiring a separate “semantic extract” button click.
- **Why it is temporary:** OCR branch is still deferred; scanned/weak-text PDFs still end as `ocr_required` until OCR acquisition is implemented.
- **Risk if left behind:** Upload latency increases (OpenAI call); if OpenAI key is missing or rate-limited, users may see `parse_response` absent and `pipeline_error` set even for otherwise “digital” PDFs.
- **Cleanup target:** Full locked pipeline: OCR branch implemented; semantic mapping runs after acquisition for both branches; background job option or async queue if latency becomes an ops concern.
- **Removal trigger / when safe to clean:** Once OCR acquisition exists and the upload pipeline has stable retries/timeouts + observability.
- **Status:** open

---

### Phase 2/3 parser guardrails + normalization layer (broker/reference/appointments/trailer/temp)

- **Type:** parser bridge / deterministic post-AI repair
- **Location(s):**
  - `app/services/load_lab_semantic.py` (post-AI guardrails + reference ranking + cleanup)
  - `app/services/load_lab_diagnostics.py` (reference candidates, document identity heuristics)
  - `app/scripts/load_lab_eval_6pdf.py` + `docs/load_lab_eval_fixtures_demo6.json` (evaluation harness + fixtures)
- **Why it was introduced:** Ensure the canonical `parse_response` stays workspace-safe while iterating on extraction quality; prevent known failure modes (Landstar/Wilson broker flattening, RXO reference confusion, trailer/type swaps, label-as-value pollution).
- **What is deterministic vs AI-driven vs post-AI repair:**
  - **AI-driven**: schema-based extraction from OpenAI into `LoadDocumentParseResponse` candidate fields.
  - **Deterministic (pre-AI evidence)**: `parse_diagnostics` packet (zones/mentions/numerics/references + grounding matches + score buckets).
  - **Deterministic post-AI repair (this entry)**:
    - **Broker**: ranked document-identity vs broker-labeled conflict override; MC-over-customs override; optional broker display-name normalization (grounded display preferred; conservative normalization like RXO legal entity → RXO).
    - **References**: extract/rank `Order #`, `Load #`, prefixed tokens like `LZ179967`; downrank decimals and weight/qty/rate/miles-adjacent values; set canonical `broker_load_reference` and preserve alternates in `extracted.references`.
    - **Trailer**: prevent `53 ft` landing in `trailer_type`; infer `trailer_type` from `equipment_type` when missing.
    - **Temperature**: clear `temperature_requirement` when it is a section label (e.g. “Special Temp Instructions”).
    - **Appointments**: normalize `appointment_type` separately from `appointment_time_text` (APPT vs FCFS parsing).
- **Why it is temporary:** These guardrails are “safety rails” while the core extraction improves; long-term goal is fewer overrides with stronger upstream evidence + grounding.
- **Risk if left behind:** Behavior becomes a patchwork of heuristics; subtle drift between semantic model behavior and deterministic corrections; harder to reason about failures.
- **Cleanup target:** Promote the strongest rules into the normalized package + prompt contract and shrink post-AI repair to only clear false positives (label-as-value) and enforce contract invariants.
- **Removal trigger / when safe to clean:** After broader PDF evaluation set shows stable broker/reference/stop accuracy without frequent overrides and confidence downgrades.
- **Status:** open

---

## Changelog

| Date (UTC) | Change |
|------------|--------|
| 2026-04-19 | Initial ledger created; seeded with known Load Lab v1 shortcuts from implementation pass. |
| 2026-04-19 | OpenAI smoke (CLI + tenant-admin `POST /load-lab/openai-smoke` + Lab UI button). |
| 2026-04-19 | Locked Load Lab v1 slice: removed promote/reject and candidate JSON; switched Lab to text acquisition + readability gate only. |
| 2026-04-20 | Load Lab v2: semantic extract endpoint + httpx OpenAI bridge + tenant columns `semantic_*` / `semantic_validation_result` (see `docs/LOAD_LAB_V2_IMPLEMENTATION_REPORT.md`). |
| 2026-04-20 | Load Lab v3: heuristic confidence + contradiction flags + `lab_review_*` columns; reuses `contradictions` JSONB for flag list (see `docs/LOAD_LAB_V3_IMPLEMENTATION_REPORT.md`). |
| 2026-04-20 | Product lock: Lab candidate must stay `LoadDocumentParseResponse` + shared workspace form goal — `docs/LOAD_LAB_WORKSPACE_PARITY_NOTE.md`, audit plan §0, first-migration §9. |
| 2026-04-20 | Workspace form parity slice: shared `applyLoadDocumentParseResponse` + read-only `LoadWorkspaceForm` on Load Lab (`docs/LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md`). |

---

### Load Lab: disabled `<fieldset>` for read-only workspace form

- **Type:** UI bridge
- **Location(s):** `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx` (`readOnly` prop wraps form in `<fieldset disabled>`)
- **Why it was introduced:** One reliable switch to disable all native controls (inputs, selects, buttons) for Load Lab without editing dozens of `disabled={}` attributes.
- **Why it is temporary:** If we later need mixed read-only + interactive controls on the same form surface, replace with per-control `disabled` driven by section policy.
- **Risk if left behind:** Styling quirks on some browsers for disabled fieldsets; screen reader semantics differ slightly vs `aria-readonly` patterns.
- **Cleanup target:** Optional unified `formMode: "edit" | "readonly" | "lab"` with explicit disabled matrix.
- **Removal trigger / when safe to clean:** Never urgent; revisit only if product asks for partial interactivity inside Lab form.
- **Status:** open

---

### Load Lab UI: JSON panels instead of `LoadWorkspaceForm` (temporary vs parity lock)

- **Type:** UI bridge
- **Location(s):** `apps/web/src/pages/LoadLabPage.tsx` (run list, `JsonBlock` previews, review UI); contrast with `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx` + `LoadWorkspacePage` PDF apply path.
- **Why it was introduced:** Fastest v1/v2 slice: prove persistence, semantic extract, and review gates without coupling Lab to full workspace state machines (brokers list, dirty tracking, save).
- **Why it is temporary:** Product rule (audit plan §0): operators should see the **same field groups** as production load entry, with Lab-only panels **additive** — not a parallel “lab editor” mental model.
- **Risk if left behind:** Operators treat JSON blobs as the source of truth; field naming drift vs workspace; promote (when it returns) harder to reason about.
- **Cleanup target:** Extract shared `applyLoadDocumentParse…` from `LoadWorkspacePage` + mount **read-only** `LoadWorkspaceForm` on Lab (see `docs/LOAD_LAB_WORKSPACE_PARITY_NOTE.md`).
- **Removal trigger / when safe to clean:** After Lab page renders workspace form sections from the same helper used by workspace PDF parse, with sections frozen read-only until promote.
- **Status:** deferred (main form path now uses `LoadWorkspaceForm`; JSON panels remain as **secondary** lab context only — see `LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md`).

---

### Load Lab v3 review engine: substring / regex heuristics (no ML)

- **Type:** parser bridge
- **Location(s):** `app/services/load_lab_review.py` (`build_lab_review_payload`, `REVIEW_ENGINE_VERSION`)
- **Why it was introduced:** Operators need a transparent, cheap gate before any promote flow — confidence by group and obvious contradiction flags from `(raw_full_text, parse_response)` only.
- **Why it is temporary:** Heuristics will false-positive/negative on messy PDFs; long-term plan may add evidence spans, model-reported confidence, or a second-pass checker.
- **Risk if left behind:** Operators treat `candidate_ok` as “production safe”; MC/DOT regex misses formatted edge cases.
- **Cleanup target:** Optional evidence offsets, tunable thresholds per tenant, integration tests on fixture PDFs.
- **Removal trigger / when safe to clean:** When promote pipeline defines authoritative validation + human sign-off paths.
- **Status:** open
