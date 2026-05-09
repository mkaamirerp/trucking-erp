# Current PDF load paths and gaps

**Scope:** Factual summary of **today’s** load-related PDF and document handling in the repo (default branch / deployed line). This is an **investigation checkpoint**, not a specification for new code in this document.

For the **approved target** pipeline (fingerprinting, classification, canonical JSON, AI mapping, OCR fallback, gates, persistence of evidence), see [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md).

**Related:**

- [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) — proposed async job + polling for **Load Page** `POST /loads/parse-document` (**design / future only** — not implemented; synchronous parse remains current).
- [`MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md`](./MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md) — multi-document load candidate, grouping, and merge design contract (not implemented yet; applies beyond current single-document Lab/workspace paths).
- [`LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`](./LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md) — design + **as-implemented** Load Lab notes.
- [`LoadLabCleaner.md`](./LoadLabCleaner.md) — temporary bridges and cleanup ledger.
- [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md) — future OpenAI integration (not wired to parsing yet).

---

## 1. Summary

Load-related PDF behavior is **split across multiple HTTP routes and parser implementations**. There is **no** single `load_document_parse.py` module on current `main`; the **Load Page** parse route uses **`parse_load_workspace_document_orchestrated`** → **`parse_pdf_bytes_to_load_document_response`** (`app/services/load_document_parse_orchestrator.py`, `load_document_product_parser.py`, `load_document_parse_guarded.py`). **Load Lab** uses **`app/services/load_lab.py`** (normalized package + semantic extraction path for a workspace-shaped `parse_response` — not the same code path as a monolithic legacy file).

**Email / Gmail intake** uses **`apply_email_pdf_intake`** (`app/services/email_engine/intake_service.py`): unified broker resolution, optional **`parse_pdf_bytes_to_load_document_response`** for a **review snapshot** (truncated `raw_text` in stored detail), plus QR hooks. **`app/services/email_intake_pdf.py`** supplies **PDF text extraction and MC/DOT hint helpers** only — not a separate TQL-only gate. **`apply_email_pdf_intake` does not create `Load` rows** (guardrail tests).

**Manual “create draft load” from intake review** (`create_draft_load_from_review_thread`) does **not** run full PDF-to-load-column parsing; it resolves broker via **`resolve_booking_broker_for_email_intake`** and MC/DOT hints from subject/snippet, and may take **`broker_load_reference`** from review **`detail_json.guarded_parse.extracted`** when present.

Operators therefore see **inconsistent** outcomes for the **same file** depending on **where** it enters the system and **which** code path runs — and, for Lab vs workspace, whether results are **persisted and versioned** or **client-only**. A **single canonical extraction brain** across all surfaces is still **not** achieved (§4–5).

---

## 2. Route table (current reality)

| Route (concept) | Frontend entry | Frontend API helper | Backend route | Parser / service | File persisted? | Parse timing | State hydrated |
|-----------------|----------------|---------------------|---------------|------------------|-----------------|----------------|----------------|
| **Manual load workspace PDF parse** | `apps/web/src/pages/LoadWorkspacePage.tsx` — `onParseWorkspacePdf`, hidden PDF input | `apps/web/src/api.ts` — `parseLoadWorkspaceDocument` → `POST /api/v1/loads/parse-document` | `app/routers/loads.py` — `parse_load_workspace_document` | **`parse_load_workspace_document_orchestrated`** → **`parse_pdf_bytes_to_load_document_response`** (product / guarded parser stack; schemas in `app/schemas/load_document_parse.py`) | **No** (request body processed; not stored as load document by this endpoint) | **Synchronous** | **Client draft only** — React workspace state (broker snapshots, refs, equipment, rate/miles, stops, etc.). `email_thread_id` / `load_id` form fields are **echo-only** in response `context`. |
| **Load Lab — PDF upload / review / promote** | `apps/web/src/pages/LoadLabPage.tsx`; nav **Load Lab** → `/loads/lab` | `apps/web/src/api.ts` — `uploadLoadLabRun`, `listLoadLabRuns`, `getLoadLabRun`, `promoteLoadLabRun`, etc. → `POST /api/v1/load-lab/runs/upload` (and sibling `/load-lab/*` routes) | `app/routers/load_lab.py` → `app/services/load_lab.py` | **`ingest_pdf_and_run_pipeline`**: PDF text via `extract_text_and_pages_from_pdf_bytes`, normalized package on run, then **`load_lab_semantic`** semantic mapping to workspace-shaped **`LoadDocumentParseResponse`** (digital path); promote is explicit | **Yes** — tenant tables `load_lab_extraction_runs`, `load_lab_promote_audits` (Alembic tenant revision `l9a8b7c6d5e4`) | **Synchronous** | **Persisted run** + JSON panels in UI; **no** operational load write until **explicit promote** (`create_draft` / `update_existing`). |
| **Email / Load Intake — upload PDF to thread** | `apps/web/src/pages/LoadInboxPage.tsx` — `handleUploadDocumentChange`; `apps/web/src/components/intake/IntakeVerificationPanel.tsx` wires the same upload handler | `apps/web/src/api.ts` — `uploadPdfToEmailThread` → `POST /api/v1/email-threads/{thread_id}/upload-pdf` | `app/routers/email_threads.py` → `app/services/email_threads.py` — `upload_pdf_to_intake_thread` | After storage: **`recompute_email_thread_intake`** → **`apply_intake_routing_for_email_thread`** (alias of **`apply_email_pdf_intake`**, `app/services/email_intake_routing.py` → `intake_service.py`): broker **`resolve_booking_broker_for_email_intake`**; PDF bytes → **`parse_pdf_bytes_to_load_document_response`** for **intake review snapshot** (not Load Page hydration); **`email_intake_pdf.py`** for **`extract_pdf_text_bytes`** / **`extract_broker_mc_dot_hints`** (supplemental resolver hints); QR via `email_intake_qr_decode` / `email_intake_qr_extractions` | **Yes** — tenant object storage (`save_upload`, module `email_intake`, synthetic `EmailMessage` + `EmailMessageAttachment`) | **Synchronous** in the upload request (includes recompute) | **Email thread** — `intake_bucket`, `confidence_level` / `confidence_score`, `routing_reason`; **`EmailIntakeReview`** with guarded-parse detail; **does not** auto-create **`Load`** inside **`apply_email_pdf_intake`** |
| **Email thread intake recompute** | `LoadInboxPage.tsx` — `handleRecomputeIntake` | `recomputeEmailThreadIntake` → `POST /api/v1/email-threads/{thread_id}/recompute-intake` | `email_threads.recompute_email_thread_intake` | Same as upload: **`apply_email_pdf_intake`** + `sync_email_intake_review_for_thread` | No new file unless attachments already exist | **Synchronous** | Same as upload — refreshes thread intake classification and review rows; **no** automatic new **`Load`** from this path |
| **Gmail sync / post-ingestion** | Operator or job triggers Gmail pull (e.g. delta from inbox UI); not a dedicated “parse PDF” button | Various sync endpoints | `app/services/email_engine/message_router.py` — `route_after_ingestion` → `run_post_ingest_intake` | Gmail: **`apply_email_pdf_intake`** (when access token present); other providers: **`apply_review_only_mailbox_intake`** | Attachments stored during message persistence (outside this summary’s per-line detail) | **After** messages are in DB | Thread intake fields + review sync; **no** `Load` auto-creation from **`apply_email_pdf_intake`** |
| **Create draft load from intake review** | `IntakeVerificationPanel` / `LoadInboxPage` — create draft flow | `createDraftLoadFromEmailThread` → `POST /api/v1/email-threads/{thread_id}/create-draft-load` | `email_threads.create_draft_load_from_email_thread` → **`app/services/email_threads.py`** — `create_draft_load_from_review_thread` | **`extract_broker_mc_dot_hints`** on subject+snippet; broker resolution **`resolve_booking_broker_for_email_intake`**; **`broker_load_reference`** from review **`detail_json.guarded_parse.extracted`** when present; **no** full PDF column mapping into `Load` here | N/A for this action’s core logic | **Synchronous** | **New `Load`** row + `EmailThread.linked_load_id` — **explicit operator action**, not Gmail PDF intake automation |
| **Link existing load to thread** | Intake UI | `linkLoadToEmailThread` | `link_load_to_email_thread` | No PDF parse | N/A | Synchronous | Thread ↔ load association |

**Important:** The **Load Page** HTTP helper **`parse_load_workspace_document_orchestrated`** (and the **Lab** pipeline in `load_lab.py`) are **not** the same binary entrypoint as **`apply_email_pdf_intake`**. Email upload / recompute / post-ingest intake call **`apply_email_pdf_intake`**, which uses **`parse_pdf_bytes_to_load_document_response`** for **review snapshots**, not for direct **Load Workspace** hydration. **Create-draft-load** is a **separate** explicit path. **Async job + poll** for Load Page parse is **design-only** — see [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md).

---

## 3. Why operators see inconsistent behavior

1. **Same PDF, different code:** **Load Page** uses **`parse_load_workspace_document_orchestrated`** → guarded product parser; **Load Lab** uses **`load_lab.py`** normalized package + **semantic** mapping; **email intake** uses **`apply_email_pdf_intake`** → **`parse_pdf_bytes_to_load_document_response`** for **review detail** (truncated storage) with **different** UX and persistence. Paths **converge on the `LoadDocumentParseResponse` contract family** in places but **not** on one shared orchestration layer.
2. **Same expectation, different guarantees:** The workspace path hydrates the **main form**; operators expect **rate-con fidelity**. Extraction is still **not** a unified document-classified pipeline; confidence semantics vary by path.
3. **Create draft ≠ parse PDF:** “Create draft from review” builds a **`Load`** from **broker resolution + review snapshot fields**, not a full PDF-to-columns map. A PDF on the thread may appear in **intake review** via **`apply_email_pdf_intake`** without feeding the **same** mapping as **Load Page** “Parse PDF.”
4. **Split “brains”:** There is **no single canonical extraction package** or shared mapping layer across **all** entry points — hence **no single place** to fix “wrong broker ref” for **everything**.

---

## 4. Biggest current gaps

| Gap | Description |
|-----|-------------|
| **Split parser paths** | **Guarded product parser** (Load Page + intake review snapshot) vs **Load Lab** semantic pipeline vs **subject/snippet + review detail** (manual draft). Different orchestration, persistence, and gates. |
| **Heuristic / model weakness** | Guarded + Lab paths still risk **over-broad** or **first-match** field behavior without a **single** document-type classifier across routes — fine for controlled demos; **not** a unified production extraction standard. |
| **Route inconsistency** | One UI speaks “parse this PDF into my load”; another path “ingest this PDF for intake review.” They **sound** unified but **are not** the same pipeline. |
| **Over-broad field extraction** | Examples in code: **first** email/phone in file as “broker contact”; aggressive **rate** dollar pattern; **first** `load`/`ref`-style token as broker reference; **first** “miles” numeric pattern. |
| **Stop list quality** | Dense or ambiguous PDF layout can still yield **many** low-value or duplicate stop-like rows depending on path (model/heuristic behavior); operators should treat extraction as **candidate** data until verified on the Load Page. |
| **No one canonical extraction brain** | No shared **normalized document package**, **classification**, or **TruckERP-owned JSON** step across routes — so fixes in one path **do not** propagate to others. **Load Lab** persists a **normalized package** shape for its route only; intake and workspace do not consume that artifact yet. |
| **Lab vs workspace duplicate entry** | Two HTTP surfaces can call the **same** `parse_load_workspace_from_pdf_bytes` with different persistence and limits — risks **divergent** product rules (rate limits, RBAC, max bytes) unless kept intentionally aligned. See [`LoadLabCleaner.md`](./LoadLabCleaner.md). |

---

## 5. Decision (direction of record)

- The **current Load Page parse** (`POST /loads/parse-document` via **`parse_load_workspace_document_orchestrated`** / guarded parser) is **not** the final **unified** architecture. It remains an **interim** hydration surface until a single pipeline exists.
- **Future direction** is **one canonical pipeline** that produces **TruckERP-owned JSON** (with deterministic validation, confidence, and contradictions), then an **apply/review** decision — as described in [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md).
- **OpenAI schema mapping** to that canonical JSON is the **planned primary extraction brain** for semantics; local logic handles **gates, validation, and orchestration**, not ad hoc per-broker regex as the long-term sole source of truth.
- **OCR / AWS-style text acquisition** is the **planned fallback** when the readability gate finds weak or scanned text — still feeding the **same** normalized package and mapping contract.
- **Implementation remains phased:** document the target, map current gaps, ship **Load Lab** as the controlled surface, then plan explicit cutover for workspace/intake — **without** removing existing routes or silently replacing operator flows until an explicit cutover plan exists.

---

## 6. Related code index (quick reference)

| Area | Key files |
|------|-----------|
| Workspace parse API | `app/routers/loads.py`, `app/services/load_document_parse_orchestrator.py`, `app/services/load_document_product_parser.py`, `app/services/load_document_parse_guarded.py`, `app/schemas/load_document_parse.py` |
| Workspace parse UI | `apps/web/src/pages/LoadWorkspacePage.tsx`, `apps/web/src/api.ts` (`parseLoadWorkspaceDocument`), `apps/web/src/loadWorkspace/loadParse*.ts` |
| Load Lab API + service + models | `app/routers/load_lab.py`, `app/services/load_lab.py`, `app/services/load_lab_semantic.py`, `app/schemas/load_lab.py`, `app/models/load_lab.py`, migration `alembic_tenant/versions/l9a8b7c6d5e4_load_lab_extraction_tables.py` |
| Load Lab UI | `apps/web/src/pages/LoadLabPage.tsx`, `apps/web/src/api.ts` (`uploadLoadLabRun`, …), `apps/web/src/routes.ts` (`OPS.LOAD_LAB`), `apps/web/src/components/TopNav.tsx` |
| Email PDF upload / recompute | `app/routers/email_threads.py`, `app/services/email_threads.py`, `app/services/email_intake_routing.py` |
| Gmail / email PDF intake | `app/services/email_engine/intake_service.py` (`apply_email_pdf_intake`, `run_post_ingest_intake`), `app/services/email_intake_pdf.py` (text + MC/DOT helpers) |
| Post-ingestion routing | `app/services/email_engine/message_router.py`, `app/services/email_engine/message_classifier.py` |
| Manual draft from review | `app/services/email_threads.py` — `create_draft_load_from_review_thread` |
