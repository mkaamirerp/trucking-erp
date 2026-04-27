# Current PDF load paths and gaps

**Scope:** Factual summary of **today’s** load-related PDF and document handling in the repo (default branch / deployed line). This is an **investigation checkpoint**, not a specification for new code in this document.

For the **approved target** pipeline (fingerprinting, classification, canonical JSON, AI mapping, OCR fallback, gates, persistence of evidence), see [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md).

**Related:**

- [`MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md`](./MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md) — multi-document load candidate, grouping, and merge design contract (not implemented yet; applies beyond current single-document Lab/workspace paths).
- [`LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`](./LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md) — design + **as-implemented** Load Lab notes.
- [`LoadLabCleaner.md`](./LoadLabCleaner.md) — temporary bridges and cleanup ledger.
- [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md) — future OpenAI integration (not wired to parsing yet).

---

## 1. Summary

Load-related PDF behavior is **split across multiple HTTP routes and parser implementations**. **Two** routes can drive **`app/services/load_document_parse.py`** end-to-end from PDF bytes today: the **load workspace** parse (ephemeral) and **Load Lab** (persisted runs). Email intake uses **`app/services/email_intake_pdf.py`** plus **`app/services/email_engine/intake_service.py`** (TQL gate, broker resolution, optional auto-load creation). **Manual “create draft load” from intake review** does **not** parse PDF text into load columns — it resolves broker and reference mostly from **email subject/snippet** and thread text.

Operators therefore see **inconsistent** outcomes for the **same file** depending on **where** it enters the system and **which** code path runs — and, for Lab vs workspace, whether results are **persisted and versioned** or **client-only**.

---

## 2. Route table (current reality)

| Route (concept) | Frontend entry | Frontend API helper | Backend route | Parser / service | File persisted? | Parse timing | State hydrated |
|-----------------|----------------|---------------------|---------------|------------------|-----------------|----------------|----------------|
| **Manual load workspace PDF parse** | `apps/web/src/pages/LoadWorkspacePage.tsx` — `onParseWorkspacePdf`, hidden PDF input | `apps/web/src/api.ts` — `parseLoadWorkspaceDocument` → `POST /api/v1/loads/parse-document` | `app/routers/loads.py` — `parse_load_workspace_document` | `app/services/load_document_parse.py` — `parse_load_workspace_from_pdf_bytes` | **No** (request body processed; not stored as load document by this endpoint) | **Synchronous** | **Client draft only** — React workspace state (broker snapshots, refs, equipment, rate/miles, stops, etc.). `email_thread_id` / `load_id` form fields are **echo-only** in response `context`. |
| **Load Lab — PDF upload / review / promote** | `apps/web/src/pages/LoadLabPage.tsx`; nav **Load Lab** → `/loads/lab` | `apps/web/src/api.ts` — `uploadLoadLabRun`, `listLoadLabRuns`, `getLoadLabRun`, `promoteLoadLabRun`, etc. → `POST /api/v1/load-lab/runs/upload` (and sibling `/load-lab/*` routes) | `app/routers/load_lab.py` → `app/services/load_lab.py` | Same **regex** parser: `parse_load_workspace_from_pdf_bytes` (plus Lab orchestration: normalized package, statuses, dedupe, promote into loads) | **Yes** — tenant tables `load_lab_extraction_runs`, `load_lab_promote_audits` (Alembic tenant revision `l9a8b7c6d5e4`) | **Synchronous** | **Persisted run** + JSON panels in UI; **no** operational load write until **explicit promote** (`create_draft` / `update_existing`). |
| **Email / Load Intake — upload PDF to thread** | `apps/web/src/pages/LoadInboxPage.tsx` — `handleUploadDocumentChange`; `apps/web/src/components/intake/IntakeVerificationPanel.tsx` wires the same upload handler | `apps/web/src/api.ts` — `uploadPdfToEmailThread` → `POST /api/v1/email-threads/{thread_id}/upload-pdf` | `app/routers/email_threads.py` → `app/services/email_threads.py` — `upload_pdf_to_intake_thread` | After storage: **`recompute_gmail_intake_for_thread`** → `apply_intake_routing_for_gmail_thread` → **`app/services/email_engine/intake_service.py`** — `apply_gmail_tql_intake_gate`; PDF text via **`app/services/email_intake_pdf.py`** (`extract_pdf_text_bytes`, `tql_digital_pdf_high_confidence`, `extract_tql_rate_con_hints`, `guess_broker_load_reference`); QR via `email_intake_qr_decode` / `email_intake_qr_extractions`; broker via `broker_intake_unified` / `broker_intake_resolve` | **Yes** — tenant object storage (`save_upload`, module `email_intake`, synthetic `EmailMessage` + `EmailMessageAttachment`) | **Synchronous** in the upload request (includes recompute) | **Email thread** — `intake_bucket`, `confidence_level` / `confidence_score`, `routing_reason`; may **create and link** a `Load` row on **high-confidence TQL digital PDF** path |
| **Email thread intake recompute** | `LoadInboxPage.tsx` — `handleRecomputeIntake` | `recomputeEmailThreadIntake` → `POST /api/v1/email-threads/{thread_id}/recompute-intake` | `email_threads.recompute_email_thread_intake` | Same as upload: **`apply_gmail_tql_intake_gate`** + `sync_email_intake_review_for_thread` | No new file unless attachments already exist | **Synchronous** | Same as upload — refreshes thread intake classification and linked load when policy creates one |
| **Gmail sync / post-ingestion** | Operator or job triggers Gmail pull (e.g. delta from inbox UI); not a dedicated “parse PDF” button | Various sync endpoints | `app/services/email_engine/message_router.py` — `route_after_ingestion` → `run_post_ingest_intake` | Gmail: **`apply_gmail_tql_intake_gate`**; other providers: **`apply_review_only_mailbox_intake`** | Attachments stored during message persistence (outside this summary’s per-line detail) | **After** messages are in DB | Thread intake fields; optional **persisted** load on TQL auto path |
| **Create draft load from intake review** | `IntakeVerificationPanel` / `LoadInboxPage` — create draft flow | `createDraftLoadFromEmailThread` → `POST /api/v1/email-threads/{thread_id}/create-draft-load` | `email_threads.create_draft_load_from_email_thread` → **`app/services/email_threads.py`** — `create_draft_load_from_review_thread` | **`extract_broker_mc_dot_hints`** on subject+snippet; **`guess_broker_load_reference`** on subject+snippet; broker resolution **`resolve_booking_broker_for_email_intake`**; **no** `load_document_parse` for load body | N/A for this action’s core logic | **Synchronous** | **New `Load`** row + `EmailThread.linked_load_id`; internal notes from thread excerpt |
| **Link existing load to thread** | Intake UI | `linkLoadToEmailThread` | `link_load_to_email_thread` | No PDF parse | N/A | Synchronous | Thread ↔ load association |

**Important:** **`parseLoadWorkspaceDocument` / `load_document_parse.py` is not invoked** by email upload, recompute, sync, or create-draft-load. It **is** used for (1) **Parse PDF** on **`LoadWorkspacePage`**, and (2) **Load Lab** uploads (`POST /api/v1/load-lab/runs/upload`). Intake paths remain separate unless explicitly integrated later.

---

## 3. Why operators see inconsistent behavior

1. **Same PDF, different code:** Workspace manual parse and **Load Lab** both run **`load_document_parse.py`** (broad global regex on full extracted text) but differ in **persistence, audit, and promote**. Inbox/TQL automation runs **`email_intake_pdf.py`** with a **narrow TQL high-confidence gate** and **different** rate/ref heuristics — and may **never** call the workspace/Lab parser.
2. **Same expectation, different guarantees:** The workspace path returns a **rich `LoadDocumentParseExtracted`** shape and fills the **main form**; operators naturally expect **rate-con fidelity**. The implementation is **not** document-classified or section-aware; **`field_confidence`** is largely `"regex"` when non-empty, which reads stronger than the heuristics are.
3. **Create draft ≠ parse PDF:** “Verify & create load” can produce a load with **broker/ref from email text**, while a PDF attached to the thread may **only** influence intake when the **Gmail TQL gate** fires — otherwise the PDF is **evidence** and routing input, not a full structured extraction into the new load row via `load_document_parse`.
4. **Split “brains”:** There is **no single canonical extraction package** or shared mapping layer today — hence **no single place** to fix “wrong broker ref” for **all** entry points.

---

## 4. Biggest current gaps

| Gap | Description |
|-----|-------------|
| **Split parser paths** | **`load_document_parse.py`** (workspace) vs **`email_intake_pdf.py` + `intake_service.py`** (Gmail intake) vs **subject/snippet heuristics** (manual draft). Different regex sets, different gates, different persistence. |
| **Manual parser global-regex weakness** | `load_document_parse.py` scans **entire** flattened PDF text with **first-match** heuristics, **no** document-type gate, **no** sectioning. Fine for demos; **not** reliable for diverse real broker PDFs. |
| **Route inconsistency** | One UI speaks “parse this PDF into my load”; another path “ingest this PDF for TQL/auto-load.” They **sound** unified but **are not** the same pipeline. |
| **Over-broad field extraction** | Examples in code: **first** email/phone in file as “broker contact”; aggressive **rate** dollar pattern; **first** `load`/`ref`-style token as broker reference; **first** “miles” numeric pattern. |
| **Stop inflation** | `_parse_stops` treats **each line** matching pickup/delivery vocabulary as a **new stop** and **always appends** a stop dict; dense or repeated wording (common on information-style sheets) yields **many** low-content stops (frontend may filter empty shells, but the **service** still emits them). |
| **No one canonical extraction brain** | No shared **normalized document package**, **classification**, or **TruckERP-owned JSON** step across routes — so fixes in one path **do not** propagate to others. **Load Lab** persists a **normalized package** shape for its route only; intake and workspace do not consume that artifact yet. |
| **Lab vs workspace duplicate entry** | Two HTTP surfaces can call the **same** `parse_load_workspace_from_pdf_bytes` with different persistence and limits — risks **divergent** product rules (rate limits, RBAC, max bytes) unless kept intentionally aligned. See [`LoadLabCleaner.md`](./LoadLabCleaner.md). |

---

## 5. Decision (direction of record)

- The **current manual workspace parser** (`load_document_parse.py` and `POST /loads/parse-document`) is **not** the final architecture. It remains an **interim** hydration helper until a unified pipeline exists.
- **Future direction** is **one canonical pipeline** that produces **TruckERP-owned JSON** (with deterministic validation, confidence, and contradictions), then an **apply/review** decision — as described in [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md).
- **OpenAI schema mapping** to that canonical JSON is the **planned primary extraction brain** for semantics; local logic handles **gates, validation, and orchestration**, not ad hoc per-broker regex as the long-term sole source of truth.
- **OCR / AWS-style text acquisition** is the **planned fallback** when the readability gate finds weak or scanned text — still feeding the **same** normalized package and mapping contract.
- **Implementation remains phased:** document the target, map current gaps, ship **Load Lab** as the controlled surface, then plan explicit cutover for workspace/intake — **without** removing existing routes or silently replacing operator flows until an explicit cutover plan exists.

---

## 6. Related code index (quick reference)

| Area | Key files |
|------|-----------|
| Workspace parse API | `app/routers/loads.py`, `app/services/load_document_parse.py`, `app/schemas/load_document_parse.py` |
| Workspace parse UI | `apps/web/src/pages/LoadWorkspacePage.tsx`, `apps/web/src/api.ts` (`parseLoadWorkspaceDocument`), `apps/web/src/loadWorkspace/loadParse*.ts` |
| Load Lab API + service + models | `app/routers/load_lab.py`, `app/services/load_lab.py`, `app/schemas/load_lab.py`, `app/models/load_lab.py`, migration `alembic_tenant/versions/l9a8b7c6d5e4_load_lab_extraction_tables.py` |
| Load Lab UI | `apps/web/src/pages/LoadLabPage.tsx`, `apps/web/src/api.ts` (`uploadLoadLabRun`, …), `apps/web/src/routes.ts` (`OPS.LOAD_LAB`), `apps/web/src/components/TopNav.tsx` |
| Email PDF upload / recompute | `app/routers/email_threads.py`, `app/services/email_threads.py` |
| Gmail intake gate | `app/services/email_engine/intake_service.py`, `app/services/email_intake_pdf.py` |
| Post-ingestion routing | `app/services/email_engine/message_router.py`, `app/services/email_engine/message_classifier.py` |
| Manual draft from review | `app/services/email_threads.py` — `create_draft_load_from_review_thread` |
