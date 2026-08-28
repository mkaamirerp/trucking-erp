# TruckERP documentation archive

This directory contains **historical implementation reports, evaluation runs, rollout plans, and superseded architecture snapshots**. These files are retained because they explain how TruckERP reached the current design, but they are **not current production guidance**.

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
- Historical files were moved without rewriting their bodies. Relative links inside them may reflect their original `docs/` location; use this README and the current master index for navigation.

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

These records remain useful for historical reasoning, regression archaeology, and understanding why current safety boundaries exist.
