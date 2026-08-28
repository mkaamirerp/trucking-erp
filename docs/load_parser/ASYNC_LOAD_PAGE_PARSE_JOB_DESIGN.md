# Async Load Page parse job design

**Status:** **DESIGN ONLY / NOT IMPLEMENTED.**  
**Scope:** Execution/transport for the production Load Page Rate Confirmation parse flow.  
**Architecture boundary:** This design wraps the **one shared Document Parser pipeline**; it does not define a new parser. Rate Confirmation remains a document profile attached to that shared parser.

**Current semantic truth:**

- [`../TruckERP_Shared_Document_Parsing_Architecture.md`](../TruckERP_Shared_Document_Parsing_Architecture.md)
- [`../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md)
- [`../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md)

---

## 1. Problem

The current Load Page PDF parse request is synchronous:

```text
LoadWorkspacePage
  → POST /api/v1/loads/parse-document
  → Load parse orchestrator / public product parser
  → shared Document Parser semantics for profile=rate_confirmation
  → LoadDocumentParseResponse
  → workspace draft hydration
```

A model call or future OCR acquisition can make that browser request slow. The async design changes **execution timing**, not parser semantics.

---

## 2. Non-negotiable contract

An async implementation must preserve:

1. **Same semantic owner** — the shared Document Parser with the Rate Confirmation profile.
2. **Same product adapter/public entrypoint** — Load feature code should continue through `app/services/load_document_product_parser.py` (or a future shared-parser API explicitly replacing it), not fork a job-specific parser.
3. **Same result family** — `LoadDocumentParseResponse`.
4. **Same production hydration** — existing Load Workspace parse → draft helper(s).
5. **No operational side effects** — parsing must not create Trips, assign equipment, change custody, dispatch, trigger driver packages, payroll, settlement, or accounting posting.
6. **Load Lab remains proving/debug infrastructure**, not the runtime job engine.

An async worker must not reintroduce `PRODUCT_PARSE_DIAGNOSTICS`, broker/carrier `role_hint` packets, ranked semantic candidate repair, or another semantic interpretation layer.

---

## 3. Proposed HTTP shape

### Create job

```text
POST /api/v1/loads/parse-document/jobs
```

Proposed behavior:

- validate upload/file limits
- persist PDF through the existing storage abstraction
- compute `input_sha256`
- create a tenant-scoped queued job
- return quickly with `job_id` and `status`

### Read/poll job

```text
GET /api/v1/loads/parse-document/jobs/{job_id}
```

Proposed terminal results:

- `succeeded` → return the validated `LoadDocumentParseResponse` result
- `failed` → return a stable error code plus redacted summary/warnings

The exact envelope (`result` nested or top-level) must be locked before implementation and then kept stable.

---

## 4. Proposed job record

Possible tenant-DB table: `load_document_parse_jobs`.

Suggested fields:

- `id`
- `tenant_id`
- `status` — `queued | running | succeeded | failed`
- `filename`
- `storage_key`
- `size_bytes`
- `input_sha256`
- `document_profile` — initially `rate_confirmation`
- parser/profile/schema/model version fields as needed for safe reuse
- `result_json` — validated parser result
- `error_code`
- `error_summary` — redacted
- `warnings_json`
- `created_by_user_id`
- `created_at`, `started_at`, `finished_at`, `updated_at`

Indexes should support tenant lookup, status/age scans, and hash/version reuse checks.

**No table or migration exists for this design today.**

---

## 5. Worker rule

The job runner should load the stored document and invoke the **same Load product parser / shared Document Parser profile** that the synchronous path uses.

Conceptually:

```text
queued job
  → read stored PDF
  → shared Document Parser(profile=rate_confirmation)
  → mechanical validation
  → LoadDocumentParseResponse
  → persist result/status
```

The worker/queue mechanism is **not locked** by this document. Acceptable future implementation choices may include a dedicated worker, scheduled runner, platform queue, or another durable mechanism. Choose based on current production operations when the slice is approved.

Do not create a parallel semantic implementation merely because execution moved out of the API request.

---

## 6. File storage and dedupe

- Store document bytes through the existing storage abstraction; keep only storage metadata/key in the job row.
- Preserve filename, size, SHA-256, tenant/source context, and relevant parser/profile versions.
- Same-byte reuse may be allowed only when the prior successful result was produced by a compatible parser/profile/schema/model version.
- Failed/incomplete jobs should not be silently reused as successful results.
- Dedupe/reuse must never silently merge unrelated Loads or email threads.

---

## 7. Frontend behavior

Proposed Load Page flow:

1. upload PDF → create job
2. UI shows parsing state while manual editing remains usable
3. poll/read job status
4. success → pass the returned `LoadDocumentParseResponse` through the existing workspace hydration path
5. failure → show warning and preserve manual workflow

Parsing success is **candidate hydration**, not operational commitment.

Save Draft / Mark Ready and all Trip/execution workflows remain separate product actions.

---

## 8. Email Intake relationship

Email Intake may eventually submit **selected** attachments to the same async parser execution path.

That does not change ownership:

- Email Intake owns relevance/routing/review/provenance.
- Document Parser owns document semantics through the selected profile.
- Load Workspace owns human verification and normal Load persistence.
- Trip/Dispatch owns execution.

The async job must not decide whether an email is load-relevant and must not become an email-specific parser.

---

## 9. Failure and recovery requirements

A future implementation should define and test:

- invalid/unsupported PDF
- OCR-required / OCR provider failure once OCR exists
- model timeout/rate-limit/transport failure
- storage failure
- parser/schema failure
- worker crash and stale `running` recovery
- retry policy
- redaction of error details and model output
- tenant isolation on every job read/write

Manual Load entry must remain usable when parsing fails.

---

## 10. Acceptance criteria for a future implementation

- Browser request no longer waits for the full semantic parse.
- Async result is the same product parser contract used by synchronous Rate Confirmation parsing.
- No semantic fork exists in the worker.
- Workspace hydration behavior remains the same.
- Jobs are tenant-scoped and recoverable.
- Result reuse is version-safe.
- Failure leaves manual Load workflow usable.
- No Load/Trip/dispatch/custody/payroll/settlement side effects are introduced by parsing.

---

## 11. Open decisions

Before implementation, explicitly decide:

- whether the synchronous endpoint remains temporarily
- job result envelope
- job retention/expiry
- parser/profile/schema/model version columns
- retry and stale-job policy
- worker/queue technology
- whether manual Load Page and Email Intake use the same job table/source metadata

None of these open decisions permits a second document-parser pipeline.
