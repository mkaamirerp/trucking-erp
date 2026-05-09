# Async Load Page parse job design (real Load Page only)

**Mode:** Design note (report-only).  
**Scope:** Real Load Page PDF parsing only — `POST /api/v1/loads/parse-document` + `LoadWorkspacePage` hydration + product guarded parser entrypoint.  
**Out of scope:** Load Lab (do not reference or modify).  
**Goal:** Stop blocking the browser request while preserving the **exact** parser contract + hydration behavior.

---

## 1. Current synchronous flow

### 1.1 Frontend call path (browser blocks)

- **Frontend API call:** `parseLoadWorkspaceDocument(file, opts)` → `fetchWithTenant('/loads/parse-document')` (multipart upload).
  - File: `apps/web/src/api.ts` (`parseLoadWorkspaceDocument`)
- **Hydration:** `LoadWorkspacePage` applies the response via:
  - `hydrateLoadWorkspaceFromParseResponse` → `applyLoadDocumentParseResponse` (draft setters).
  - Files: `apps/web/src/loadWorkspace/loadParseHydration.ts`, `apps/web/src/loadWorkspace/applyLoadDocumentParseResponse.ts`

**Why it blocks:** the browser’s `fetch()` does not resolve until the backend returns the full `LoadDocumentParseResponse`, which can include an OpenAI call inside the parser pipeline.

### 1.2 Backend endpoint (synchronous)

- **Endpoint:** `POST /api/v1/loads/parse-document`
- **Behavior:** reads bytes, validates PDF, calls orchestrator, returns response **inline**.
  - File: `app/routers/loads.py` (`parse_load_workspace_document`)

### 1.3 Orchestrator function

- **Orchestrator:** `parse_load_workspace_document_orchestrated(...)`
  - File: `app/services/load_document_parse_orchestrator.py`
- Requires `tenant_id` and `db` (route passes tenant DB session).

### 1.4 Guarded product parser entrypoint

- **Canonical entrypoint imported by orchestrator:** `parse_pdf_bytes_to_load_document_response`
  - Public import: `app/services/load_document_product_parser.py` (re-export)
  - Implementation: `app/services/load_document_parse_guarded.py`

### 1.5 Current response contract

- **Response model:** `LoadDocumentParseResponse`
  - File: `app/schemas/load_document_parse.py`
  - Root keys: `document`, `extracted`, `raw_text`, `warnings`, `field_confidence`, `context`

### 1.6 Current hydration path

- The frontend expects exactly `LoadDocumentParseResponse` and hydrates draft state via:
  - `hydrateLoadWorkspaceFromParseResponse(res, callbacks)`
  - which calls `applyLoadDocumentParseResponse(res, callbacks)`

---

## 2. Target async flow

### 2.1 New endpoints

1. **Create job (fast):** `POST /api/v1/loads/parse-document/jobs`
   - Accept multipart `file` (+ optional echo fields like `load_id` / `email_thread_id` if needed for UI context only).
   - Store PDF bytes via existing storage abstraction.
   - Compute `input_sha256`.
   - Insert job row with `status=queued`.
   - Return quickly: `job_id`, `status`, and optionally `input_sha256` / `filename`.

2. **Poll job:** `GET /api/v1/loads/parse-document/jobs/{job_id}`
   - Returns job status.
   - When `succeeded`, returns the **same** `LoadDocumentParseResponse` payload (either as top-level or nested under `result` — choose one and keep stable).
   - When `failed`, returns a redacted `error_code` + `error_summary` + `warnings_json`.

### 2.2 Worker/runner executes the same parser

- The runner loads the stored PDF bytes from storage and calls:

`parse_pdf_bytes_to_load_document_response(db, tenant_id=…, pdf_bytes=…, filename=…, openai_chat_json_schema=None)`

- It persists the validated `LoadDocumentParseResponse` JSON as `result_json`.

### 2.3 Frontend behavior

- Upload → create job (returns `job_id` immediately).
- UI enters “Parsing…” state and polls.
- On success → call existing hydration unchanged:
  - `hydrateLoadWorkspaceFromParseResponse(result, callbacks)`
- On failure → show warning and keep user in manual Load Page mode.

---

## 3. Non-negotiable constraints

Must preserve, exactly:

- **Parser function:** `parse_pdf_bytes_to_load_document_response`
- **Result shape:** `LoadDocumentParseResponse`
- **Frontend hydration:** `hydrateLoadWorkspaceFromParseResponse` / `applyLoadDocumentParseResponse`

Must not change:

- Load Lab (no codepaths, no tables, no behaviors).
- Parser prompt/logic/contract.
- Any automatic operational actions:
  - **No final load creation**
  - **No trip creation**
  - **No dispatch**
  - **No driver/truck/trailer assignment**
  - **No payroll/custody/driver package triggers**

---

## 4. Minimal job table design (recommended columns)

**Table:** `load_document_parse_jobs` (tenant DB)

- `id` (PK)
- `tenant_id` (required)
- `status` (`queued|running|succeeded|failed`)
- `filename`
- `storage_key`
- `size_bytes`
- `input_sha256`
- `result_json` (JSONB; validated `LoadDocumentParseResponse`-shaped payload)
- `error_code` (short stable string, e.g. `invalid_pdf`, `openai_timeout`, `storage_read_failed`)
- `error_summary` (redacted human-safe text, max length)
- `warnings_json` (array; optional convenience mirror; canonical warnings also live inside `result_json` on success)
- `created_by_user_id` (platform/user id string consistent with auth model)
- `created_at`
- `started_at`
- `finished_at`
- `updated_at`

### Indexes / constraints

- Index: `(tenant_id, id)`
- Index: `(tenant_id, input_sha256)`
- Index: `(tenant_id, status, created_at)`
- Optional uniqueness (conservative): do **not** enforce unique `(tenant_id, input_sha256)`; reuse is a policy decision and parser versions may evolve.

---

## 5. Storage design

- Store PDF bytes via the existing storage abstraction (same mechanism used for tenant uploads elsewhere).
- Persist **only** `storage_key` + metadata in the job row.
- Do **not** store raw PDF bytes in the DB job table.
- Preserve:
  - original `filename`
  - `size_bytes`
  - `input_sha256` (for reuse and audit)

---

## 6. SHA256 reuse / cache behavior

Conservative reuse rule:

- If the same tenant uploads an identical PDF (`input_sha256` match) and there is a **succeeded** job whose `result_json` is present, the POST endpoint may:
  - return the **existing** `job_id` immediately, or
  - return success with the existing `result_json` (but keep API shape stable).

Do not reuse:

- **Failed** jobs (unless the user explicitly requests a retry which creates a new job).
- Jobs with missing `result_json`.

Future considerations (not required for v1):

- TTL/expiry of cached results
- Versioning / invalidation if parser schema/prompt changes (store parser version fields if needed later)

---

## 7. Worker design (safest minimal option on single-host, prod-only)

Options (compare):

- **API background task:** simplest, but not durable across process restarts; competes with web workers; harder to monitor.
- **Periodic runner script:** durable and easy to observe; can claim queued jobs and process in batches.
- **Dedicated worker container:** clean separation; requires operational support (compose/service lifecycle).
- **systemd timer/loop:** fits the current host’s operational pattern (timers already exist for other jobs); clear journald visibility.

**Safest first implementation slice (recommended later):**

- A **systemd timer** that runs a **one-shot runner** in the `truckerp-api` container (similar to other operational timers on this host), processing a bounded number of queued jobs each run.

This provides durability + observability without changing the API runtime model.

---

## 8. Frontend behavior (detailed)

- **Upload starts job:** user selects PDF → POST `/jobs` → immediate `job_id`.
- **Parsing UI state:** show spinner + “Parsing…” message; user can continue manual edits while parsing runs.
- **Polling:** GET job every N seconds with backoff; stop polling on `succeeded|failed`.
- **Success:** call existing `hydrateLoadWorkspaceFromParseResponse(result, callbacks)` and show the same warnings/toolbar message logic.
- **Failure:** show warning; keep manual workflow fully usable. Do not block Save Draft / Save Ready.
- **Cancel/close:** allow user to close the parse panel without attempting to cancel the backend job (v1).
- **Duplicate upload protection:** client can hash locally later, but server-side sha256 reuse is the durable safeguard.

---

## 9. Failure handling

Non-exhaustive failure modes and expected behavior:

- **OpenAI timeout** (see existing OpenAI helper timeout defaults): set `status=failed`, `error_code=openai_timeout`.
- **Invalid / unsupported PDF:** `error_code=invalid_pdf` / `pdf_open_error`.
- **Storage read failure:** `error_code=storage_read_failed`.
- **Parser exception:** `error_code=parser_exception` with redacted summary.
- **Worker crash mid-job:** job stuck in `running`; runner must recover.
- **Stuck running job:** define a “running too long” threshold; runner can mark as failed or reset to queued for retry policy.

All error summaries must be **redacted** (no secrets, no raw OpenAI output).

---

## 10. Safety / audit

- Audit events should record:
  - job created (who, when, sha256, filename)
  - job succeeded/failed (status + error_code)
  - optional: hydration applied client-side (best-effort UI audit later)
- Explicitly state in UI and audit: hydration is **not** operational commitment.
- No downstream load/trip/dispatch/payroll/custody/package side effects.

---

## 11. Relationship to email intake (future)

- Email intake may later create parse jobs for **selected** attachments, but:
  - email intake must **filter/classify first**
  - async parser job only extracts/hydrates candidate fields
  - parser does not decide whether an email is a load

---

## 12. Acceptance criteria for future implementation

- Browser no longer waits on a long-running parse request.
- Same PDF yields the same `LoadDocumentParseResponse` contract as the current sync endpoint.
- Same LoadWorkspacePage hydration result (via existing hydration functions).
- Duplicate upload can reuse a succeeded job/result by sha256.
- Failed parse leaves manual workflow usable.
- No operational side effects (loads/trips/dispatch/assignments/payroll/custody/package).
- Tests cover `queued|running|succeeded|failed` and runner recovery.

---

## 13. Open questions

- Should the old synchronous endpoint remain temporarily for compatibility?
- Should parser version/prompt/schema versions be stored for cache invalidation?
- Should job results expire or be retained for audit?
- Should users be able to retry a failed job from the UI?
- Should email-attachment parse jobs and manual upload parse jobs share the same table?

