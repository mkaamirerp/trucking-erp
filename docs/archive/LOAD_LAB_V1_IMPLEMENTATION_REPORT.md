# Load Lab v1 slice — implementation report (grounded)

**Scope implemented:** The first real Load Lab v1 slice only: upload → persist run → text acquisition → readability gate → normalized package + warnings → UI inspection.

**Explicitly not implemented (by design lock):** OCR execution, OpenAI semantic extraction into candidate JSON, promote to operational loads, inbox integration, or any operational load writes.

Related docs: `docs/LOAD_LAB_FIRST_MIGRATION_CUT.md`, `docs/PDF_LOAD_PIPELINE.md`, `docs/CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`, cleanup ledger `docs/LoadLabCleaner.md`.

---

## What was implemented

### 1) PDF upload from Load Lab

- **UI route:** `/loads/lab` (`apps/web/src/pages/LoadLabPage.tsx`)
- **API route:** `POST /api/v1/load-lab/runs/upload` (`app/routers/load_lab.py`)

### 2) `load_lab_extraction_runs` persistence

Runs are persisted in tenant DB table **`load_lab_extraction_runs`** (already present from earlier migration work).

### 3) File hash / metadata capture

On upload we persist:

- `file_sha256` (SHA-256 of uploaded bytes)
- `filename`, `mime_type`, `file_size_bytes`
- `source_route` and `created_by_platform_user_id`

### 4) Readability gate (v1)

Implemented as a minimal gate:

- **`text_usable`** → stored as `status="text_extracted"` and `extraction_path="digital"`
- **`ocr_required`** → stored as `status="ocr_required"` and `extraction_path="ocr_required"` when extracted text is empty/whitespace
- **`failed`** → stored as `status="failed"` for non-PDF or unrecoverable extraction errors

No OCR is executed in v1; `ocr_required` is a **classification output** only.

### 5) Local text extraction + normalized text package

- Local PDF text extraction uses `pypdf` via `_extract_text_from_pdf_bytes`.
- A normalized package is persisted as JSONB in `normalized_package` with:
  - file metadata
  - extraction method label (`pypdf_text_v1`)
  - `raw_full_text` (truncated at a cap; truncation logged into warnings)
  - warnings

### 6) Persist run state + warnings + versions

Run rows persist:

- status progression: `uploaded` → `deduped` → (`text_extracted` | `ocr_required` | `failed`)
- warnings from PDF open/page extraction + any truncation warning
- version pins: `parser_version`, `schema_version`, `prompt_version`, `model_name`, `normalizer_version`, `ocr_engine_version` (null)

### 7) Load Lab UI panels (v1)

The UI shows:

- run status (readability derived from status)
- file info (mime, size)
- file hash (SHA-256)
- readability decision (`text_usable` / `ocr_required` / `failed`)
- normalized package JSON panel
- raw text preview panel (first chunk of `raw_full_text`)
- warnings + errors (`warnings`, `pipeline_error`)

---

## API surface (v1)

Load Lab router now exposes:

- `POST /api/v1/load-lab/runs/upload`
- `GET /api/v1/load-lab/runs`
- `GET /api/v1/load-lab/runs/{run_id}`
- `POST /api/v1/load-lab/openai-smoke` (tenant admin only; connectivity only; not part of extraction)

Removed from Lab to honor scope lock:

- promote endpoints
- reject endpoints
- promote-audit listing endpoint

---

## Temporary bridges / shortcuts (logged)

See `docs/LoadLabCleaner.md` entries for:

- Importing private `_extract_text_from_pdf_bytes` (temporary acquisition bridge)
- Removal of promote/reject/candidate JSON for v1 lock

---

## Verification performed on this host

- Frontend build succeeded (`npm run build`), nginx rebuilt via `scripts/reload_nginx_web.sh`.
- API rebuilt/restarted via `scripts/reload_api.sh`.
- Running nginx bundle contains the “Raw text preview” UI string (proof that UI shipped).
- Running API router contains only upload/list/get plus OpenAI smoke (no promote/reject paths).

---

## Next investigation track (not implementation)

From here, the investigation track should decide the next migration cut among:

- OCR acquisition (Textract-class path) feeding the same normalized package
- OpenAI schema mapping step inserted after normalized package in Load Lab
- classification/relevance improvements
- re-introducing promote only after semantic + validation gates are in place

