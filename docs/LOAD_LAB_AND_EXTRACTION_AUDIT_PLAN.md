# Load Lab and Extraction Audit Plan

This document captures the **accepted direction** and **implementation status** for an isolated PDF/load extraction testing and review surface (“Load Lab” / “Load Test”). Locked design decisions below remain authoritative; **v1 is shipped** — subsequent edits should record **delta** (new capabilities vs design debt).

**Related:**

- [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) — **grounded** alignment vs divergence + smallest next UI step (no promote).
- [`LOAD_LAB_FIRST_MIGRATION_CUT.md`](./LOAD_LAB_FIRST_MIGRATION_CUT.md) — smallest safe first slice definition (v1 alignment + next cuts).
- [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md) — target pipeline stages and how Lab maps to them (§7).
- [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — factual route map including Lab vs workspace vs intake.
- [`LoadLabCleaner.md`](./LoadLabCleaner.md) — temporary shortcuts; **update in the same PR** when adding new debt.
- [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md) — OpenAI wiring (not yet part of Lab parse).

**Boundary:** Load Lab must **not** silently replace main load workspace or intake flows. Broader integration (e.g. “suggest from PDF” on `LoadWorkspacePage`) requires its own **cutover** decision and should stay off until explicitly approved.

---

## 0. Workspace parity lock (product — 2026-04-20)

Load Lab exists for **isolation, audit, and safe rollout** — **not** as a second final load-editing product with its own field model.

| Rule | Statement |
|------|-------------|
| **Same canonical candidate** | The **final** candidate payload Lab targets for human review must remain the **same TruckERP parse/hydration contract** the real Load workspace uses for PDF-derived data today: **`LoadDocumentParseResponse`** (and the same downstream mapping intent toward **`LoadWritePayload`** / **`Load`**). **Do not** introduce a parallel “lab-only final load schema” for that candidate. |
| **Lab-only data** | Run tracking, pipeline metadata, model I/O, **confidence**, **contradictions**, raw text, and JSON debug views may remain **Lab-specific** columns/JSON — they are audit/review overlays, not a replacement load row. |
| **Same editing surface (goal)** | The operator should recognize the **same field groups / sections** as **`LoadWorkspaceForm`** (`apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx`). Lab may stay on **`/loads/lab`**, but the **hydrated** candidate should be shown through that **shared** form experience (typically **read-only** until promote exists), with Lab panels **beside or below**, not replacing the form. |
| **No default operational write** | Same form does **not** imply silent save: **no** `POST/PATCH` loads from Lab by default; **promote** remains an explicit later action when implemented. |

See [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) for what already matches the repo vs what still diverges.

---

## 1. Purpose

- Provide an **isolated document extraction and testing workspace**, separate from normal load entry.
- Offer a **safe environment** for debugging parsers, prompts, and paths (digital vs OCR) without risking dispatch, settlement, or payroll.
- Support **controlled rollout**: validate extraction quality and audit completeness before any broader integration.

---

## 2. Why this is needed

- **Current PDF-related routes and behavior are split** across surfaces, which makes consistent review and versioning harder.
- The **current manual parser is not reliable enough** to be the sole ingestion surface for business-critical load fields.
- **Bad extraction cascades** into downstream operational and financial modules; wrong load fields must not propagate silently.

---

## 3. Page / module concept

**Working names:** Load Lab, or Load Test.

**Shipped —** UI route **`/loads/lab`** (`apps/web/src/pages/LoadLabPage.tsx`), TopNav **Load Lab**.

- **Separate route** from the main Load workspace (isolation preserved).
- **Upload** PDF (`POST /api/v1/load-lab/runs/upload`); list/detail runs; optional **OpenAI semantic extract** and **v3 lab review** (confidence + contradiction flags); connectivity smoke for tenant admins.
- **Shows** extraction path, normalized package, **candidate JSON** (`parse_response` as **`LoadDocumentParseResponse`**), semantic/review metadata, warnings, and debug JSON panels.
- **Promote / reject:** **not** exposed in the current API/router slice; table **`load_lab_promote_audits`** remains for when explicit promote returns. **No** default write to operational **`loads`** from Lab uploads.

**Parity gap (intentional until next UI cut):** Lab still uses **JSON-centric** layout rather than mounting **`LoadWorkspaceForm`**; closing that gap is the **smallest shared-form** step (see [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md)) — **without** turning Lab into a different final schema.

**Still proposed / future:**

- Image upload and non-PDF gates as in full pipeline doc.
- Stronger contradiction UX and evidence spans.
- Field-level promote (partial accept) per locked promote audit intent.

---

## 4. Locked design decisions — core direction

The following are **locked** for this design:

| Decision | Statement |
|----------|-----------|
| Isolation | **Separate isolated** Load Lab page/module; not the primary ingestion path for production load entry until explicitly integrated. |
| Database | **Same tenant DB** as today’s operational data (no requirement for a second database instance for Lab). |
| Canonical output | **Same canonical parse/hydration types** as the Load workspace PDF path (**`LoadDocumentParseResponse`** → existing mapping toward **`Load` / `LoadWritePayload`**). Lab must **not** fork a second “final” load DTO for the candidate. |
| Persistence | **Separate persistence** for extraction **runs** and **audit** data (dedicated tables or clearly scoped entities), not default mutation of core operational load rows. |
| Writes to loads | **No default direct write** into operational `loads` (or equivalent) from Lab pipelines. |
| Promotion | **Explicit promote action only** — operator-initiated (or future policy-gated) step to apply candidate data to a real load. |

---

## 5. DB / persistence design

**Principles:**

- **Lab-specific tables** hold extraction payloads, run metadata, evidence structures, versioning fields, and promote audit rows.
- **Operational load tables** are updated **only** through the explicit promote flow (and existing production services where appropriate), not implicitly on every upload or parse.

**Implemented tables (tenant DB):**

- **`load_lab_extraction_runs`** — one row per upload/run (tenant-scoped): status lifecycle, version pins, file hash/metadata, `normalized_package`, `parse_response`, `ai_model_output`, `field_evidence`, `contradictions`, `warnings`, `dedupe_prior_run_id`, etc. (Alembic revision **`l9a8b7c6d5e4`**.)
- **`load_lab_promote_audits`** — one row per promote attempt (outcome, target load, fields accepted/blocked structure — v1 often stores `["*"]` until granular promote exists).

**Optional future:** **`load_lab_extraction_events`** (or similar) if run-level status is not enough.

**Relationship to “same tables”:** Reuse **canonical types and validation** in application code (`LoadDocumentParseResponse`, `LoadCreate` / `LoadUpdate` on promote); operational **`loads`** rows are not written except via **explicit promote**.

---

## 6. Run state machine

Document a **clear run lifecycle** with statuses. Example set (exact enum names may be adjusted at implementation time; semantics are locked):

| Status | Meaning (summary) |
|--------|-------------------|
| `uploaded` | File accepted; metadata and hash recorded. |
| `deduped` | Fingerprint/dedupe gate completed (may short-circuit to prior result or branch). |
| `text_extracted` | Digital text path produced usable text per gates. |
| `ocr_required` | Readability gate determined OCR is needed. |
| `ocr_complete` | OCR path finished; normalized package available. |
| `classified` | Document classification step completed (coarse type). |
| `mapped` | AI schema mapping (or equivalent) produced structured output. |
| `validated` | Deterministic validation completed (schema + business rules). |
| `review_required` | Confidence/contradiction gates or policy flagged human review before promote. |
| `promoted` | Explicit promote succeeded; link to target load recorded in promote audit. |
| `rejected` | Operator or policy rejected the run; no promote. |
| `failed` | Unrecoverable error in pipeline; no candidate for promote. |

**Notes:**

- Not every run visits every state (e.g. digital path may never enter `ocr_required`).
- `review_required` may coexist with partial candidate display; policy defines whether promote is blocked until cleared.

---

## 7. Versioning

**Every extraction run must persist** (at minimum):

| Field | Role |
|-------|------|
| `parser_version` | Parser / orchestration code identity. |
| `schema_version` | Canonical TruckERP JSON schema version used for mapping/validation. |
| `prompt_version` | Prompt template / instruction bundle version. |
| `model_name` | Model identifier (provider + model string). |
| `ocr_engine_version` | OCR engine/build when OCR path used; null or N/A when digital-only. |
| `normalizer_version` | Version of the component that builds the normalized document package. |

These fields support **reproducibility**, regression comparison, and safe **rerun** policy when versions change.

---

## 8. Promote flow and promote audit

**Promote** is a **first-class audited action**, not an implicit save.

**Promote audit must capture:**

- `run_id` — source extraction run.
- **Operator** — identity of the user performing promote (or system if policy-automated in the future).
- **Promote target type** — e.g. create draft load vs update existing load.
- **`target_load_id`** — if applicable (nullable for aborted attempts per product rules).
- **Fields accepted** — which candidate fields were applied (or a structured summary).
- **Fields blocked** — which fields were withheld (policy, low confidence, contradiction).
- **Overwrite decisions** — explicit record when existing load data could have been overwritten and what rule allowed or denied it.

Promote audit rows may live in a **dedicated table** or in the **central audit spine** if the platform consolidates there; see [§9 Central audit alignment](#9-central-audit-alignment).

---

## 9. Central audit alignment

Load Lab should **align with the project’s central audit spine direction**:

- **Lab-specific tables** retain **extraction payloads**, **run metadata**, **evidence structures**, and **versioning** (optimized for debugging and reparse).
- **Broader audit visibility** (who did what, when, on which tenant) should still **fit the central audit philosophy** (e.g. promote and high-signal operator actions visible in the same operational audit story as other sensitive mutations).

Implementation detail (event bus vs table vs both) is deferred; the **design lock** is: **no orphan lab-only silo** that contradicts org-wide audit expectations.

---

## 10. Evidence model

**Do not store only final candidate JSON.**

Where practical, preserve **per field or per group** evidence, for example:

| Element | Description |
|---------|-------------|
| Extracted value | Value proposed for the canonical field. |
| Confidence | Field- or group-level score or band. |
| Contradiction flags | Signals that conflict with other fields or external hints. |
| Evidence snippet | Short verbatim span supporting the extraction. |
| Page number | If available from PDF/OCR layout. |
| Extraction method | Digital text vs OCR vs inferred, etc. |

**Groups** may mirror pipeline thinking (e.g. broker identity, contacts, references, equipment, money, stops, customs).

This supports **debugging**, **operator trust**, and **safe reparse** without guessing from a single JSON blob.

---

## 11. Artifact storage note

If **normalized text** or **model payloads** become **large**:

- Design should allow **storage pointers** (e.g. object storage key + checksum) instead of forcing a single overloaded DB row.
- **Split persistence** is acceptable: run row for metadata + versions + summary; child table or blob store for page texts, raw full text, or full model I/O.

The **contract lock** is: the **logical normalized package shape** stays stable; **physical storage** may shard for size and performance.

---

## 12. Idempotency / rerun policy

Document **rerun behavior** clearly:

| Scenario | Policy (design intent) |
|----------|-------------------------|
| Same file hash | **By default**, do not create **noisy duplicate runs** — dedupe or attach to prior run per product rules (operator may still request explicit reprocess). |
| Parser / prompt / schema version change | **Reruns allowed** and should be **tracked** as a new run (or a **versioned rerun** linked to prior run_id) so comparisons are possible. |
| Explicit operator rerun | Always **tracked** as a **new run** or a **versioned rerun** with operator attribution; never silent overwrite of audit history. |

**Idempotency** at promote: promote actions should be **idempotent or safely rejectable** where duplicate promote of the same run could corrupt loads (implementation detail deferred).

---

## 13. Audit / log design (summary)

**Track for every extraction run** (in addition to versioning in §7):

- File **content hash**
- **Source route** / entry context (e.g. Load Lab vs future embedded entry)
- **Tenant**
- **OCR used or not** (and engine version when used)
- **Extracted / candidate JSON** (canonical-shaped)
- **Confidence** by section/field (structure as per evidence model)
- **Contradictions** and **warnings**
- **Operator actions** (review notes, accept/reject, rerun)
- **Outcome** — terminal state from state machine (`promoted`, `rejected`, `failed`, etc.)

**Promote** is covered in §8.

---

## 14. Safety boundaries

- **Do not auto-write** directly into production operational loads **by default** from Lab.
- **Candidate draft / review-first** model: Lab shows and persists candidates and evidence; operational truth moves only on **explicit promote** (or future **proven safe** automated rules — out of scope until separately designed and accepted).
- **Trusted / user-confirmed fields** must not be overwritten by weak extraction without **strong evidence** and explicit policy (aligned with PDF pipeline principles).

---

## 15. Relationship to future PDF pipeline

- **Load Lab** is the **controlled surface** for rolling out the **future canonical PDF pipeline** described in `docs/PDF_LOAD_PIPELINE.md` (or successor).
- The canonical flow should end in **TruckERP-owned JSON**, not PDF-native field names.
- **OpenAI** (or equivalent) remains the **semantic mapping brain**; **OCR/AWS** remains **fallback** for weak-text or scanned files.
- Lab implements **review, versioning, and audit** before that pipeline is wired into the main Load workspace.

---

## 16. Migration approach

- **Current manual parse** should **not** be treated as the **final** ingestion surface.
- **Load Lab** becomes the **first controlled rollout area**: ship Lab + persistence + audit + promote behind permissions; iterate on quality and gates.
- Broader integration (e.g. “suggest fields from PDF” inside main load UI) only after Lab proves extraction and audit adequacy.

---

## 17. Pitfalls to avoid

- Defaulting Lab uploads into **operational load rows** without promote.
- **One global confidence score** with no field/group evidence.
- **Missing contradiction handling** or silent auto-apply on conflict.
- **OCR vs digital branches** returning **different JSON shapes** (must converge on canonical contract before promote).
- **Undersized DB rows** or single JSON column for **unbounded** artifacts without pointer/split strategy.
- **Duplicate runs** for the same hash with no dedupe or rerun lineage.
- **Promote actions** not visible in **central audit** philosophy.
- Treating **schema-valid** JSON as **business-safe** without deterministic validation gates.

---

## 18. Current status

**Direction (locked):** Isolated Load Lab module, same tenant DB, **same canonical parse DTO** as workspace PDF hydration (**`LoadDocumentParseResponse`**), separate run/audit persistence, **no default operational load writes**, explicit promote only when that feature is (re-)enabled, with run state machine, full versioning, evidence model, promote audit table, central audit alignment, artifact storage flexibility, and clear idempotency/rerun policy. **Workspace parity lock (§0):** Lab must not become a **different final editing experience**; shared **`LoadWorkspaceForm`** presentation is the **target**, with Lab-only panels additive.

**Implemented (repo today):** Tenant migrations through **`k9j8h7g6f5e4`** (Lab v3 review columns); API prefix `/api/v1/load-lab` — upload, list, detail, **semantic extract**, **lab-review recompute**, OpenAI smoke; UI `/loads/lab` with JSON + review UI; digital text path + optional OpenAI mapping into **`parse_response`**; **promote/reject routes not wired** in current slice; hash-based dedupe reuse for identical version pins.

**Known gaps (track in [`LoadLabCleaner.md`](./LoadLabCleaner.md)):** No OCR execution; **`LoadLabPage` does not yet mount `LoadWorkspaceForm`** (parity debt); duplicate HTTP entry point to parser brain vs workspace `parse-document`; promote UI/API deferred.

**Investigation / migration next:** Shared **`applyLoadDocumentParseResponse…`** helper + read-only **`LoadWorkspaceForm`** on Lab route (see [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md)); then decide intake/workspace read-only suggest under RBAC — record in `CURRENT_PDF_LOAD_PATHS_AND_GAPS.md` + `LoadLabCleaner.md` when work starts.
