# Load Lab — Current Pipeline Flow (End-to-End)

This document describes the **current** Load Lab pipeline end-to-end using **exact module/function names**.

It also clearly distinguishes:
- **Canonical output**: fields that affect the final `parse_response.extracted` values.
- **Diagnostics-only**: fields stored under `parse_response.parse_diagnostics` (do **not** affect workspace hydration unless explicitly merged into extracted fields by the semantic service).

---

## 1) Upload / run creation flow

### Entry point (API)
- **Route**: `app/routers/load_lab.py`
  - `upload_run(...)` → `POST /api/v1/load-lab/runs/upload`

### Run creation + dedupe
- **Service**: `app/services/load_lab.py`
  - `ingest_pdf_and_run_pipeline(...)`
    - Computes file hash (sha256)
    - Optionally reuses a prior run via `_find_reusable_run(...)`
    - Creates a new `LoadLabExtractionRun` row otherwise

### Run storage model
- **Model**: `app/models/load_lab.py`
  - `class LoadLabExtractionRun`
    - `normalized_package` (JSONB)
    - `parse_response` (JSONB)
    - semantic metadata: `semantic_*` columns
    - lab review metadata: `lab_confidence`, `lab_review_status`, etc.

**Boundary:** Load Lab does **not** create operational loads. It persists **runs** only.

---

## 2) PDF text extraction / normalized text flow

### Text extraction
- **Service**: `app/services/load_document_parse.py`
  - `_extract_text_and_pages_from_pdf_bytes(pdf_bytes) -> (raw_text, page_texts, warnings)`

### Normalized package structure
- **Service**: `app/services/load_lab.py`
  - `_build_normalized_package(...) -> dict`
    - `raw_full_text` (truncated to `_MAX_RAW_TEXT_STORED`)
    - `page_texts[]` with `{page, text}`
    - `warnings[]`

### Persist normalized text
- **Service**: `app/services/load_lab.py`
  - `ingest_pdf_and_run_pipeline(...)` stores `normalized_package`
  - Sets run `status` to:
    - `text_extracted` for text-usable digital PDFs
    - `ocr_required` for unreadable PDFs (OCR branch exists but is not final; see boundaries below)

---

## 3) Broker grounding and broker confidence matrix flow

### Parse diagnostics packet (Phase 1 evidence)
- **Module**: `app/services/load_lab_diagnostics.py`
  - `build_parse_diagnostics(...) -> dict`
    - `party_mentions`
    - `authority_candidates`
    - `numeric_candidates`
    - `reference_candidates`
    - `document_zones`, `stop_block_candidates`

### Broker directory grounding (tenant DB)
- **Module**: `app/services/load_lab_grounding.py`
  - `ground_party_mentions_to_brokers(db, tenant_id, party_mentions, authority_candidates) -> list[dict]`
    - Produces `broker_directory_matches[]`
    - Matches by: `mc`, `dot`, `known_sender_email`, `domain`, `alias`, `contact_phone`

### Broker confidence matrix (diagnostics-only)
- **Module**: `app/services/load_lab_broker_matrix.py`
  - `load_broker_match_signals(db, tenant_id) -> dict`
    - Tenant signals from:
      - `BrokerDomain`, `BrokerKnownSender`, `BrokerAlias`, `BrokerContact.email` domain, `Broker.mc_number/dot_number`
    - Global signals from **platform DB** (via `app.core.database.AsyncSessionLocal`):
      - `GlobalBookingBroker*` approved rows (domains/aliases/known-senders/MC/DOT)
  - `build_broker_confidence_matrix(diag, raw_text, signals) -> list[dict]`
    - Writes `parse_diagnostics.broker_confidence_matrix`
    - Candidate rows include:
      - scoring dimensions (explicit label, doc identity, payer/bill-to, agreement counterparty, contact domain, authority context, directory grounding, carrier penalty)
      - evidence/negative factors, matched domains/emails/MC/DOT, role contexts, blocking decisions

**Diagnostics-only:** The matrix is **not** used for workspace hydration directly; it is stored under `parse_diagnostics`.

---

## 4) Authority candidate / MC-DOT role classification flow

### Extraction + role hinting
- **Module**: `app/services/load_lab_diagnostics.py`
  - `_authority_candidates(page_texts) -> dict`
    - Produces `authority_candidates.entries[]` with:
      - `value`
      - `kind` (legacy: `mc` / `dot`)
      - `type` (`MC` / `DOT`)
      - `page`, `line_index`
      - `surrounding_text`
      - `nearby_company_candidate`
      - `role_hint`: `broker_context` / `carrier_context` / `unknown`
      - `reason_for_role_hint`

### Broker grounding consumes authority candidates
- **Module**: `app/services/load_lab_grounding.py`
  - `ground_party_mentions_to_brokers(...)`
    - Accepts either `entry["type"]` or `entry["kind"]`
    - Resolves brokers via `app.services.brokers.resolve_broker_by_authority(...)`

---

## 5) Semantic extraction flow (OpenAI) with three modes

### Entry point (API)
- **Route**: `app/routers/load_lab.py`
  - `semantic_extract(...)` → `POST /api/v1/load-lab/runs/{run_id}/semantic-extract`
  - Query params:
    - `force` (bool)
    - `mode` (string): `guarded` | `ai_validate_only` | `pure_ai`

### Core semantic extraction
- **Module**: `app/services/load_lab_semantic.py`
  - `semantic_extract_run(db, tenant_id, run_id, force=False, mode="guarded")`

### Mode behavior
- **`guarded`**
  - Sends `parse_diagnostics` JSON to the model (as hints)
  - Runs post-AI guardrails/repairs (Section 8)
  - Adds diagnostics enrichment (broker email provenance, broker matrix, references acceptance tables, etc.)

- **`ai_validate_only`**
  - Sends `parse_diagnostics` JSON to the model (as hints)
  - **Skips** post-AI guardrails/repairs
  - Still performs AI JSON coercion + schema validation (Section 6)

- **`pure_ai`**
  - Sends **only** the extracted PDF text (no diagnostics hints)
  - **Skips** post-AI guardrails/repairs
  - Still performs AI JSON coercion + schema validation (Section 6)

The selected mode is persisted as:
- `parse_response.context.load_lab_semantic_mode`

---

## 6) AI JSON coercion / validation flow

### Model call
- **Module**: `app/services/load_lab_semantic.py`
  - `_openai_chat_json_schema(...)`
    - Uses OpenAI `response_format=json_schema` when supported
    - Falls back to `response_format=json_object` when `json_schema` returns HTTP 400
  - `_parse_openai_payload(data) -> (content_json_str, usage, error)`

### Coercion + strict validation
- **Module**: `app/services/load_lab_semantic.py`
  - `_coerce_model_payload_to_schema(obj) -> dict`
    - Prunes unknown keys
    - Coerces:
      - `references[]` items to `{kind, value}`
      - `stops[]` items to allowed stop fields only
  - Validates the coerced payload with:
    - `LoadLabSemanticModelOutput.model_validate(coerced)`
    - `StrictExtracted.model_validate(merged_extracted_dict)` (after deterministic reference merge)

**Canonical impact:** If coercion drops invalid shapes, those fields will not appear in final `parse_response.extracted`.

---

## 7) Reference extraction flow (deterministic, pre-OCR)

### Base candidates from diagnostics
- **Module**: `app/services/load_lab_diagnostics.py`
  - `_reference_candidates_from_pages(page_texts) -> list[dict]`
  - Added into `parse_diagnostics.reference_candidates`

### Supplemental candidates + acceptance/rejection + primary selection
- **Module**: `app/services/load_lab_reference_extract.py`
  - `augment_diagnostic_reference_resolution(diag, raw_full_text, page_texts, filename) -> merge_pack|None`
    - Extends `parse_diagnostics.reference_candidates`
    - Writes diagnostics:
      - `accepted_references`
      - `rejected_reference_candidates` (with `rejection_reason`)
      - `primary_reference_selection_reason`
      - `reference_extraction_gap_analysis`
    - Returns merge pack (not stored on `diag`) for DTO hydration

### Merge into canonical extracted fields
- **Module**: `app/services/load_lab_reference_extract.py`
  - `merge_structured_references_into_extracted_dict(extracted_dict, merge_pack) -> extracted_dict`
    - Populates `extracted.references[]`
    - Sets `extracted.broker_load_reference` if blank

**Canonical impact:** This merge happens inside `semantic_extract_run(...)` before building the final `LoadDocumentParseResponse`. It affects the canonical `parse_response.extracted`.

---

## 8) Post-AI repair / guardrail flow (guarded mode only)

These run inside `app/services/load_lab_semantic.py` **only when** `mode == "guarded"`.

Key guardrail functions include:
- `_numeric_gating_on_reference(...)`
- `_apply_reference_role_ranking(...)` (sets/overrides `broker_load_reference`, preserves alternates in `extracted.references`)
- `_cleanup_trailer_and_temp_fields(...)`
- `_normalize_stop_appointments(...)`
- `_apply_broker_display_name_normalization(...)`
- `_apply_broker_authority_context_repair(...)` (prevents carrier-context MC/DOT from filling broker fields)

Each may:
- Mutate `payload["extracted"]` (canonical)
- Add `parse_diagnostics.review_flags` (diagnostics-only)
- Add warnings and lower `field_confidence` (canonical response metadata)

---

## 9) Final `parse_response` structure (canonical vs diagnostics-only)

### Canonical (workspace-facing) fields
- **Schema**: `app/schemas/load_document_parse.py`
  - `LoadDocumentParseResponse`
    - `document.filename`
    - `extracted` (`LoadParseExtractedFields`)
      - canonical extracted scalar fields
      - `references[]` (`LoadParseReferenceItem {kind,value}`)
      - `stops[]` (`LoadParseStopItem`)
    - `raw_text`
    - `warnings[]`
    - `field_confidence{field: "low"|"medium"|...}`
    - `context{...}` including:
      - `context.load_lab_semantic_mode` (**guarded / ai_validate_only / pure_ai**)

### Diagnostics-only fields
Stored under:
- `parse_response.parse_diagnostics` (a dict assembled in `semantic_extract_run(...)`)

Includes (non-exhaustive):
- Phase 1 evidence:
  - `party_mentions`, `authority_candidates`, `numeric_candidates`, `reference_candidates`, `document_zones`, `stop_block_candidates`
- Broker evidence:
  - `broker_directory_matches`
  - `broker_confidence_matrix`
  - `broker_match_domains`
- Reference resolution:
  - `accepted_references`
  - `rejected_reference_candidates` (+ `rejection_reason`)
  - `primary_reference_selection_reason`
  - `reference_extraction_gap_analysis`
- Broker contact email provenance fields (see `build_broker_contact_email_parse_diagnostics`)
- Guardrail review artifacts:
  - `review_flags`
  - `broker_resolution_summary`
  - `reference_ranking` (from `_apply_reference_role_ranking`)

---

## 10) Canonical vs diagnostics-only (rules of influence)

### Modules allowed to influence final extracted values (canonical)
- `app/services/load_lab_semantic.py`
  - builds final `LoadDocumentParseResponse`
  - applies post-AI guardrails when `mode=="guarded"`
  - merges deterministic references into `extracted`
- `app/services/load_lab_reference_extract.py`
  - **via** merge pack consumed by `semantic_extract_run(...)`

### Diagnostics-only modules (must not directly affect hydration)
- `app/services/load_lab_diagnostics.py` (evidence packet)
- `app/services/load_lab_grounding.py` (broker match evidence)
- `app/services/load_lab_broker_matrix.py` (confidence matrix)
- `app/services/load_lab_broker_contact_email_diagnostics.py` (email provenance diagnostics)
- `app/services/load_lab_review.py` (lab confidence + contradiction flags)

---

## 11) Current known boundaries / not implemented yet

- **OCR branch not final**: `ocr_required` exists as a status, but OCR extraction is not the locked/complete path yet.
- **No operational load creation from Load Lab**: the lab persists runs + candidate JSON only.
- **No Trip container save**: Load Lab does not persist “Trips/Containers” as operational objects.
- **Load Lab remains an evaluation/safety harness**: it is used to test extraction behavior, diagnostics, and guardrails before operational workflows.

---

## 12) Next evaluation step

1. Run the **same 6 PDFs** in all three modes:
   - `guarded`
   - `ai_validate_only`
   - `pure_ai`
2. Compare:
   - `pure_ai` vs `ai_validate_only` vs `guarded`
3. Produce:
   - **field-by-field expected vs actual** (including structured `extracted.references[]` and `broker_load_reference`)
4. Identify recurring mistakes:
   - reference misclassification
   - broker vs carrier authority mixups
   - stop-level vs document-level identity confusion
5. Only after patterns stabilize, connect changes to real workspace hydration flows.

