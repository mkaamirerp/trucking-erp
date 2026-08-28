# Load Lab — historical pipeline flow snapshot

**Status:** **SUPERSEDED AS CURRENT PARSER GUIDANCE / HISTORICAL LOAD LAB SNAPSHOT.**  
**Scope:** This file records the older Load Lab diagnostic/semantic experiment pipeline and exact module boundaries used during that phase. **Load Lab is a proving/debug surface, not the product Load Page.**  
**Current product parser:** Rate Confirmation v2 is defined by [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md), [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md), and the public `load_document_product_parser` code path.  
**Current route map:** [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md).

The detailed flow below is retained for historical evaluation/debug context. Its `guarded` / `ai_validate_only` / `pure_ai`, diagnostics, broker matrix, deterministic reference merge, and post-AI repair descriptions **must not be interpreted as the production Rate Confirmation v2 semantic architecture**.

---

## 1) Upload / run creation flow (historical Lab path)

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
  - `LoadLabExtractionRun`
    - `normalized_package` (JSONB)
    - `parse_response` (JSONB)
    - semantic metadata columns
    - lab review metadata (`lab_confidence`, `lab_review_status`, etc.)

**Boundary:** Load Lab is run/evaluation storage; it does not define the production Load form or parser architecture.

---

## 2) PDF text extraction / normalized text flow

Historical Lab code extracted text and stored a `normalized_package` with full/page text and warnings. Weak/image-only PDFs could land in `ocr_required`; actual OCR remained incomplete.

This Lab normalized-package persistence was useful for evaluation, but the current product Rate Confirmation parser uses its own shipped acquisition contract and controlled OCR-required gate.

---

## 3) Broker grounding and confidence-matrix flow

Historical Lab diagnostics included:

- `party_mentions`
- `authority_candidates`
- `numeric_candidates`
- `reference_candidates`
- `document_zones`
- `stop_block_candidates`
- tenant/global broker-directory grounding
- broker-confidence-matrix scoring

These structures were Lab evidence/diagnostic experiments. They are **not** the current v2 model handoff.

---

## 4) Authority candidate / MC-DOT role classification

The Lab diagnostics layer produced MC/DOT candidate records and role hints such as `broker_context`, `carrier_context`, and `unknown`, then used them for grounding/evaluation.

The production Rate Confirmation v2 handoff deliberately forbids these pre-model role conclusions (`role_hint`, `broker_party`, `carrier_party`) as semantic input.

---

## 5) Historical semantic-extraction modes

The Lab semantic endpoint supported experiment modes such as:

- **`guarded`** — diagnostics sent as hints + post-AI repairs/guardrails.
- **`ai_validate_only`** — diagnostics sent as hints, but post-AI semantic repair skipped.
- **`pure_ai`** — PDF text only, without diagnostics hints or post-AI semantic repair.

The selected mode was recorded in Lab response context for comparison.

These were **evaluation modes**, not the current production Rate Confirmation v2 contract.

---

## 6) AI JSON coercion / validation

The Lab experiment coerced model output into the Lab/Load parse schema, pruned unknown keys, normalized references/stops, and validated via Pydantic before storing final Lab parse output.

Schema validation remains a durable principle. The current product v2 path, however, uses the production parser modules and mechanical validator described in the current architecture docs rather than this Lab orchestration.

---

## 7) Historical deterministic reference extraction

Lab diagnostics/reference modules generated candidate references, accepted/rejected lists, primary-selection reasoning, and then could merge structured references into canonical `extracted` fields.

That deterministic semantic ranking/merge strategy is historical Lab behavior. The product v2 boundary does **not** reintroduce it as a competing semantic brain.

---

## 8) Historical post-AI repair / guardrail flow

In guarded Lab mode, post-AI logic could perform semantic changes such as:

- numeric gating / reference role ranking
- broker display/authority repair
- trailer/temperature cleanup
- appointment normalization

These experiments helped expose failure modes, but they are not the current production semantic contract. Production v2 permits mechanical validation only after the model.

---

## 9) Historical `parse_response` structure

Lab stored workspace-shaped `LoadDocumentParseResponse` fields plus Lab-only diagnostics/review artifacts. The important product rule remains:

> The workspace-shaped parse DTO is candidate/hydration data; Lab diagnostics are proving metadata, not a second operational Load model.

---

## 10) Historical canonical vs diagnostics influence

The Lab pipeline distinguished fields that affected `parse_response.extracted` from diagnostics-only evidence. That distinction was useful for experiments, but many of the historical modules intentionally no longer influence the production Rate Confirmation parser.

---

## 11) Boundaries that remain useful

- **OCR execution is still not implemented** in the current product Rate Confirmation path.
- **Load Lab remains an evaluation/safety harness**, not the production Load Page.
- **Lab must not create a second parser truth** that overrides the current product profile.
- **Operational Load creation/save rules remain product actions**, not an automatic consequence of a Lab run.

---

## 12) Historical evaluation method

The old evaluation cycle compared the same PDF fixtures across `guarded`, `ai_validate_only`, and `pure_ai`, then inspected field-by-field failures such as reference classification, broker/carrier authority confusion, and stop/document identity confusion.

That history remains useful for regression thinking. New production parser tests should target the current Rate Confirmation v2 contract rather than treating these Lab modes as required product behavior.
