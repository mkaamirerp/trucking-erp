# TruckERP documentation archive

This directory contains **historical implementation reports, evaluation runs, rollout plans, superseded architecture snapshots, and unshipped prototypes**. These files are retained because they explain how TruckERP reached the current design, but they are **not current production guidance**.

## Current document-parser truth

For document parsing, use:

1. [`../TruckERP_Shared_Document_Parsing_Architecture.md`](../TruckERP_Shared_Document_Parsing_Architecture.md) — **one shared Document Parser engine/pipeline with attached document profiles**.
2. [`../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) — first shipped profile: Rate Confirmation v2.
3. [`../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — current route/integration reality.
4. [`../LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](../LOAD_LAB_WORKSPACE_PARITY_NOTE.md) — Load Lab is proving/debug/regression; `LoadWorkspaceForm` is production.

**Architecture lock:** Fuel, Toll, Rate Confirmation, and future unstructured document types attach profiles/rules/schema/context to the **same shared Document Parser pipeline**. Archived files that imply separate parser stacks, “Load Lab first” as product architecture, old diagnostics-as-brain behavior, or OpenAI-not-implemented state are historical only.

## Archive rules

- Do not use an archived file as the source of truth for current behavior.
- Do not revive an old pipeline because an archived file calls itself “current,” “definition of record,” or “direction of record.”
- Durable rules must be consolidated into a current canonical document before an old file is archived.
- Frozen regression evidence such as `../LOAD_LAB_BASELINE_6PDF.md` stays outside this archive while it remains useful to active tests/evaluation.
- `../LoadLabCleaner.md` remains outside the archive as the active cleanup ledger; individual entries must be re-audited against current parser v2/shared-parser truth.
- Historical files moved here may contain old relative links or status wording. Use current docs and the master index for present-day guidance.

## Archived in the 2026-08-28 Load Lab/parser cleanup

### Load Lab implementation / rollout history

- `LOAD_LAB_V1_IMPLEMENTATION_REPORT.md`
- `LOAD_LAB_V2_IMPLEMENTATION_REPORT.md`
- `LOAD_LAB_V3_IMPLEMENTATION_REPORT.md`
- `LOAD_LAB_FIRST_MIGRATION_CUT.md`
- `LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md`
- `LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`
- `LOAD_LAB_CURRENT_PIPELINE_FLOW.md`

### Evaluation history

- `LOAD_LAB_REAL_PDF_EVALUATION.md`
- `LOAD_LAB_CONTRACT_COMPARISON_REPORT.md`
- `LOAD_LAB_NEXT_EVAL_CYCLE.md`
- `B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md`

### Superseded parser/OpenAI architecture and rollout reports

- `PDF_LOAD_PIPELINE.md`
- `OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`

## Archived early driver decision records

Under `decisions/`:

- `0001-driver-ownership.md` — superseded by the newer driver-extension employment-relationship model.
- `0005-storage-and-ocr.md` — superseded as OCR architecture by the shared Document Parser lock.

## Archived email-intake investigation report

Under `email/`:

- `EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY_PRE_V2_REPORT.md` — detailed pre-parser-v2 mixed current/target investigation. Preserved for provider/routing archaeology; not current parser or intake architecture authority.

## Archived fixture-only illustrative outputs

Under `fixtures/load_lab/`:

- `load_lab_fixture_1pickup_3deliveries.synthetic_expected_truckerjson.json`
- `load_lab_fixture_3pickups_1delivery.synthetic_expected_truckerjson.json`

These two JSON files explicitly described themselves as illustrative expected output and were not consumed by current code/tests. The matching PDFs and `.lab_parse_response.json` golden compatibility inputs remain active under `../fixtures/load_lab/` because current tests reference them.

## Archived database-schema snapshots

Under `db_schema/legacy_db_schema_smoke_2026_01/`:

- `README.md`
- `tenant_smoke_active__schema.md`
- `tenant_smoke_provision__schema.md`
- `trucking_erp__schema.md`

That January folder already identified itself as an archived snapshot generated under obsolete container/database assumptions.

Also under `db_schema/`:

- `schema_only.driver_era.sql` — old driver-only pg_dump containing the legacy `drivers`, `driver_phones`, and `driver_documents` era but not the current people/load/trip schema.

Neither snapshot set has current repo consumers. Current generated live-DB snapshot rules live in `../db_schema/README.md`.

These records remain useful for historical reasoning, regression archaeology, and understanding why current safety boundaries exist.
