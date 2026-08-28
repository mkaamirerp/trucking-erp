# Load Lab — first migration cut (smallest safe slice)

**Purpose:** Define the **smallest safe first implementation slice** for Load Lab: isolated **report/debug** surface, **no** broad parser rewrite, **no** inbox pipeline migration, **no** production auto-apply from intake or workspace.

**Status:** This document is the **definition of record** for that slice. A **v1 implementation** largely matches it today (see **§8**). **Do not treat this file as a coding task list** until an explicit build ticket references it.

**Related:** [`LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`](./LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md), [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md), [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md), [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md), [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md), [`LoadLabCleaner.md`](./LoadLabCleaner.md).

---

## 1. First scope

### 1.1 Which current route is the first Load Lab input

- **Primary input:** **`POST /api/v1/load-lab/runs/upload`** (multipart PDF). This is a **new** route, not a redirect of `POST /api/v1/loads/parse-document` or email-thread upload.
- **Rationale:** The first cut must **not** change intake or workspace entry points. Lab is the **only** first-class consumer of “upload → persist run → inspect” for this slice.

### 1.2 Exact user flow supported in v1

1. Operator opens **`/loads/lab`** (Load Lab page).
2. Operator uploads a **PDF** (optional: **force rerun** to bypass hash/version reuse).
3. Backend runs **digital text acquisition** (existing PDF text path) + parse into **`LoadDocumentParseResponse`** shape, builds **normalized package** JSON, persists **`load_lab_extraction_runs`** row with statuses/version pins; optional **OpenAI** semantic fill of **`parse_response`** (v2) and **v3** heuristic review columns.
4. UI lists **recent runs**; selecting a run shows **normalized package**, **parse response** (candidate JSON), review/confidence panels, warnings, and debug JSON.
5. **Promote / reject** — **deferred** in the current shipped slice (no Lab router promote/reject); **`load_lab_promote_audits`** table remains for when explicit promote is re-enabled. **No** silent write to **`loads`** from Lab.
6. When promote exists again: **promote audits** and best-effort **`audit_events`** record high-signal actions.

**Readability branch (v1):** If text is empty / image-only, run records **`ocr_required`** / **`failed`** with a clear message — **no OCR execution** in this slice (still valid “route digital vs OCR-needed” for demo and metrics).

### 1.3 Explicitly out of scope (first cut)

| Out of scope | Reason |
|--------------|--------|
| Rewriting **`load_document_parse.py`** or replacing regex with OpenAI in prod | Broad parser change; defer to a later slice after Lab proves mapping + gates. |
| **Inbox / email-thread** upload, recompute, or TQL path changes | No intake pipeline migration; avoids dispatch/settlement blast radius. |
| **Auto-apply** parsed fields into loads without user action | No production auto-apply; only explicit promote from Lab. |
| **`POST /loads/parse-document`** behavior change | Workspace stays backward-compatible; Lab is additive. |
| **Full OCR / Textract** execution | Acquisition stub only; implement when infra + cost model ready. |
| **OpenAI** wired into mapping | Integration **point** documented; **no** full semantic pipeline in this slice (see §5). |
| **Field-level promote** (`apply_all=false`) | API/UI complexity; defer while `["*"]` promote proves audit + loads integration. |

---

## 2. Reuse map

### 2.1 Frontend — reuse vs new

| Asset | Reuse? | Notes |
|-------|--------|--------|
| **Layout / shell** | **Yes** | Same `Layout` + `TopNav` as rest of tenant app; add nav link to Lab only. |
| **API helpers** | **Pattern reuse** | Same `fetchWithTenant` / `handle` pattern as `apps/web/src/api.ts`; **new** functions for `/load-lab/*`. |
| **`LoadWorkspaceForm` / workspace sections** | **Required for parity (next cut)** | v1 used a **JSON-first** `LoadLabPage` to ship quickly; **product lock** (audit plan §0) requires the **same** form sections as production, with Lab-only panels additive. Smallest step: shared **parse → draft** helper + **read-only** `LoadWorkspaceForm` on Lab (see [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md)). |
| **Design tokens / CSS** | **Yes** | Reuse existing CSS variables / button classes for consistency. |

### 2.2 Backend — reuse vs new

| Piece | Reuse? | Notes |
|-------|--------|--------|
| **`parse_load_workspace_from_pdf_bytes`** | **Yes (temporary bridge)** | Same function as workspace parse; **must** remain the only regex brain until OpenAI slice lands. |
| **`LoadDocumentParseResponse`** / Pydantic validation | **Yes** | Canonical candidate shape for v1 candidate JSON. |
| **`loads_service.create_load` / `update_load`** | **Yes** | Promote reuses **operational** load services so field rules stay one place. |
| **`write_audit_event`** | **Yes (best-effort)** | Aligns Lab with central audit spine; actor model may use workarounds until unified (see cleaner ledger). |
| **Email intake services** | **Do not reuse** for Lab v1 | Keeps slice isolated from `email_threads` / `intake_service`. |
| **`POST /loads/parse-document` router** | **Do not extend** for Lab | Lab has **own** router; avoids coupling and accidental shared middleware side effects. |

### 2.3 Must not reuse directly (guardrails)

- **Do not** call email **`upload_pdf_to_intake_thread`** from Lab upload — different persistence, side effects, auto-load policy.
- **Do not** persist Lab runs on **`loads`** or **`email_threads`** rows as scratch fields.
- **Do not** log or persist **OpenAI API keys** in run JSON or generic app logs.

---

## 3. New persistence

### 3.1 Minimal first tables (v1)

| Table | Role |
|-------|------|
| **`load_lab_extraction_runs`** | One row per upload/run: tenant, hash, file metadata, **status**, **version pins**, `normalized_package`, `parse_response`, `field_evidence`, `warnings`, `contradictions`, optional `ai_model_output` (null in v1), `dedupe_prior_run_id`, `pipeline_error`, timestamps. |
| **`load_lab_promote_audits`** | One row per promote attempt: run id, operator, target type, target load id, outcome, fields accepted/blocked blobs, `request_id`. |

**Migration reference (implemented):** `alembic_tenant/versions/l9a8b7c6d5e4_load_lab_extraction_tables.py`.

### 3.2 Fields in v1 vs later

| In **v1** | **Later** (not required for smallest demo) |
|-----------|---------------------------------------------|
| Status lifecycle through `validated` / `review_required` / `failed` / `rejected` / `promoted` | Finer event stream table (`load_lab_extraction_events`) |
| Version strings: `parser_version`, `schema_version`, `prompt_version`, `model_name`, `normalizer_version`, optional `ocr_engine_version` | Distinct sentinels vs real model ids; migration to normalize historical rows |
| `normalized_package` JSONB (with raw text size cap / truncation warning) | **S3 / pointer** for large payloads; child table for per-page blobs |
| `parse_response` as candidate JSON | Separate **`ai_model_output`** populated when OpenAI exists |
| `field_evidence` list (regex-derived) | Richer evidence (page, snippet) from layout/OCR |
| Promote audit with `fields_accepted` often `["*"]` | Accurate per-field accept/block arrays |

---

## 4. New API surface

### 4.1 Minimal lab endpoints — definition vs shipped

**Smallest theoretical slice** would be: **upload**, **get run**, **list runs** (read-only demo).

**v1 as shipped** adds endpoints justified by the audit plan without expanding intake/workspace:

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/v1/load-lab/runs/upload` | Ingest PDF, run pipeline, return run + `reused_existing_run`. |
| `GET` | `/api/v1/load-lab/runs` | List recent runs (tenant-scoped). |
| `GET` | `/api/v1/load-lab/runs/{run_id}` | Run detail for UI. |
| `POST` | `/api/v1/load-lab/runs/{run_id}/semantic-extract` | OpenAI structured candidate into **`parse_response`** (tenant-scoped). |
| `POST` | `/api/v1/load-lab/runs/{run_id}/lab-review` | Recompute v3 confidence + contradiction flags (no OpenAI). |
| `POST` | `/api/v1/load-lab/openai-smoke` | **Tenant admin only** — OpenAI `GET /v1/models` connectivity; **no** PDF parse (optional smoke beyond minimal upload/read slice). |

**Promote / reject in first doc revision:** Were specified for an end-to-end safety demo; **current shipped slice** omits those HTTP routes — persistence for promote audit remains for a **later** explicit promote cut.

**Not in current slice:** Webhooks, batch reparse, cross-tenant admin, public unauthenticated upload, **promote/reject API** (until re-scoped).

---

## 5. OpenAI integration point (future + smoke only)

### 5.1 Where the future OpenAI call belongs in the Lab flow

Per [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md) and [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md):

1. After **`normalized_package`** is built (and optionally after stub classification/relevance).
2. **Before** treating output as final: run **deterministic validation** on model JSON (same contract as today’s `parse_response` or a stricter canonical schema).
3. Persist raw model output in **`ai_model_output`**, bump **`model_name`** / **`prompt_version`**, append token usage into run or audit context when available.

**Code locus (implemented):** OpenAI semantic mapping lives in **`app/services/load_lab_semantic.py`**, invoked from **`POST /load-lab/runs/{id}/semantic-extract`** — **not** from `POST /loads/parse-document` (workspace parse route stays separate).

### 5.2 Where a smoke-test wrapper should live first

**Implemented:**

- **CLI:** `python -m app.scripts.openai_smoke` (inside API container with `/run/secrets/truckerp.env` sourced) — `httpx` GET `https://api.openai.com/v1/models`.
- **HTTP (tenant admin only):** `POST /api/v1/load-lab/openai-smoke` — same probe; **Load Lab** UI shows **“Test OpenAI connectivity”** for tenant-admin roles only.

**No full pipeline:** Smoke proves key + network only; it does **not** implement schema mapping, chunking, or promote integration.

---

## 6. Smallest end-to-end demo

**Goal:** First **truly useful** demo proves persistence, inspection, and safety boundaries — not “best extraction.”

1. **Upload PDF** on `/loads/lab` → `POST /api/v1/load-lab/runs/upload`.
2. **Route:** Response shows **`extraction_path`** (`digital` vs `ocr_required` for unusable text) and **`status`** (`validated`, `review_required`, or `failed`).
3. **Store run:** Row exists in **`load_lab_extraction_runs`** with **`file_sha256`**, version pins, **`normalized_package`**, **`parse_response`**.
4. **Show normalized package** in UI (JSON panel).
5. **Show candidate JSON** = **`parse_response`** (v1: regex-backed `LoadDocumentParseResponse` shape).
6. **Show warnings / confidence:** **`warnings`** array; **`field_evidence`** (regex confidence); **`contradictions`** array (may be empty in v1).
7. **Audit:** Reload run via **`GET .../runs/{id}`**; when promote/reject ship again, confirm **`load_lab_promote_audits`** and **`audit_events`** (best-effort) for those actions.

**Success criteria:** No change to inbox or workspace behavior; no load row unless operator **promotes**; operators can answer “what did we extract, when, with which parser version?”

---

## 7. Risks / pitfalls

| Risk | Mitigation (first cut) |
|------|-------------------------|
| **Copied UI drift** | Keep Lab UI small; track shared-component extraction in [`LoadLabCleaner.md`](./LoadLabCleaner.md). |
| **Duplicate route drift** | Document shared limits (max bytes, PDF magic) for Lab vs `parse-document`; align intentionally or log divergence as debt. |
| **Temp bridges** | Parser bridge to `load_document_parse.py` is explicit debt — same cleaner file. |
| **Schema / version drift** | Always persist **`parser_version`**, **`schema_version`**, **`prompt_version`**, **`model_name`**, **`normalizer_version`** on run; bump when behavior changes. |
| **Oversized JSON blobs** | Truncate `raw_full_text` in normalized package with a clear warning; plan pointer storage before large OCR payloads. |
| **Accidental writes to operational loads** | Only **`loads_service`** on **promote**; no Lab code path that “auto-saves” a load on upload; integration tests / manual checklist on promote. |

---

## 8. As-implemented snapshot (v1 alignment)

The following already exists in the repo and matches this document’s **first cut** intent (with noted deltas):

- **UI:** `apps/web/src/pages/LoadLabPage.tsx`, route **`/loads/lab`**, TopNav link.
- **API:** `app/routers/load_lab.py` — upload, list, detail, **semantic-extract**, **lab-review**, **openai-smoke** (see §4.1).
- **Services:** `app/services/load_lab.py` (ingest + text path); **`load_lab_semantic.py`** (v2); **`load_lab_review.py`** (v3 heuristics).
- **Models / migrations:** `app/models/load_lab.py`; tenant revisions through **`k9j8h7g6f5e4`** (semantic + review columns).
- **OpenAI smoke CLI:** `app/scripts/openai_smoke.py`.

**Delta vs older §4.1 text:** **Promote/reject** HTTP handlers are **not** in the current router slice.

---

## 9. Workspace parity (product lock — supersedes “JSON-only Lab” as final UX)

Load Lab is **not** a second product surface for editing loads with a different final field model.

- **Candidate JSON** in **`parse_response`** must stay **`LoadDocumentParseResponse`** (same as **`POST /loads/parse-document`**), then map to workspace draft state using the **same** rules the workspace uses (ideally **one shared helper** — see [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md)).
- **UI goal:** **`LoadWorkspaceForm`** sections (read-only until promote), with Lab-only run/debug/review panels **around** them — separate **route** is fine.
- **Writes:** still **no** operational load save by default; promote remains **explicit** when implemented.

**Next migration cuts** (separate decisions): **Shared-form Lab UI** (§9), OCR acquisition, inbox or workspace read-only suggest, field-level promote — each should get a short addendum or successor doc when scoped.
