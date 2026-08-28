# Current PDF load paths and gaps

**Status:** **CURRENT REALITY MAP — verified 2026-08-28 against `inspect/current-working-state-2026-08-28`.**  
**Scope:** Factual map of the current Load / Rate Confirmation PDF entry points and the boundaries between the product parser, Email Intake, and Load Lab.  
**Product rule:** **Load Lab is a proving / debug surface, not the product Load Page.** The production editable load form is `LoadWorkspaceForm`.

**Current parser truth:**

- [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md) — shared acquisition / semantic boundary.
- [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) — implemented Rate Confirmation v2 profile and frozen handoff contract.
- [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) — Lab vs production Load Page boundary.

`PDF_LOAD_PIPELINE.md` and the old OpenAI integration report are retained as historical design/rollout records; they are not current parser implementation authority.

---

## 1. Summary

There is now a **canonical public product parser entrypoint** for Load / Rate Confirmation PDFs:

```text
app/services/load_document_product_parser.py
  → parse_pdf_bytes_to_load_document_response(...)
  → app/services/load_document_parse_rate_con.py
```

That product path is **Rate Confirmation v2**:

```text
PDF
→ page acquisition / embedded-text usability classification
→ controlled OCR-required gate when needed
→ cached tenant_identity_exclusion
+ frozen Rate Confirmation field_rules
+ page-separated text
→ OpenAI schema mapping
→ mechanical validation
→ LoadDocumentParseResponse
```

The product path does **not** use `PRODUCT_PARSE_DIAGNOSTICS`, `broker_party`, `carrier_party`, `role_hint`, ranked semantic candidates, or the old diagnostics-driven semantic repair stack.

Two important product surfaces now converge on that public parser:

1. **Load Page / Load Workspace PDF parse** — hydrates the production workspace draft.
2. **Email Intake PDF review snapshot** — calls the same public parser, but stores the result as review evidence and does **not** auto-create a Load.

**Load Lab remains separate by design.** It has persisted runs, historical diagnostic/semantic experiment modes, review metadata, and lab-only controls. It is useful for regression and proving work, but it is **not** the source of truth for the current production Rate Confirmation parser.

---

## 2. Current route / ownership table

| Flow | Current parser / service | Persistence / effect | Product meaning |
|---|---|---|---|
| **Load Page PDF parse** — `POST /api/v1/loads/parse-document` | `parse_load_workspace_document_orchestrated(...)` → public product parser → Rate Confirmation v2 | Endpoint itself does not create/update a Load; result hydrates client workspace draft state | **Production Load Page parse path** |
| **Email Intake PDF upload / recompute** | `apply_email_pdf_intake(...)` → `load_document_product_parser.parse_pdf_bytes_to_load_document_response(...)` for review snapshot, plus email-specific broker-resolution / QR / duplicate checks | Persists intake/review state and attachment metadata; **no automatic Load creation** inside PDF intake | **Production intake review path using the same Rate Confirmation product parser for PDF semantics** |
| **Create draft Load from intake review** | Explicit email-thread action; uses intake review / broker-resolution state rather than silently treating attachment ingestion as a Load save | Creates a Load only after explicit operator action | **Separate product action; not the PDF parser itself** |
| **Load Lab upload / semantic evaluation** | `app/services/load_lab.py` + Lab-specific semantic/diagnostic modules and persisted run models | Persists `load_lab_extraction_runs` and Lab review/debug state; any promote behavior is explicit Lab tooling | **Proving / regression surface — not production parser truth** |
| **Async Load Page parse job** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) | Not implemented in this snapshot | **Future transport/execution model; does not change parser semantics** |

---

## 3. What is shared now

### 3.1 Public product parser

Feature code that needs product PDF → `LoadDocumentParseResponse` semantics should use:

```text
app/services/load_document_product_parser.py
```

That module explicitly points to the Rate Confirmation v2 production implementation. The Load Workspace and Email Intake review path both use that public contract.

### 3.2 Output / hydration contract

The product parser returns the existing `LoadDocumentParseResponse` / `LoadParseExtractedFields` family. The production Load Page maps that DTO into workspace draft state; it does not treat the parse DTO as the persisted `Load` row itself.

### 3.3 Shared acquisition principles

Rate Confirmation v2 classifies per-page embedded-text usability and blocks semantic parsing when OCR is required. Weak/scanned pages are **not** sent as blank/garbage evidence to OpenAI and do **not** fall back to the legacy diagnostics parser.

---

## 4. What is intentionally still separate

### Load Lab

Load Lab is an experiment and regression harness. It may retain historical diagnostics, comparison modes, persisted run metadata, JSON panels, or evaluation-only controls that do not belong on the production Load Page.

The rule is:

> **Do not fix the product parser by making Load Lab the product.** Fix the canonical parser/profile, then use Lab to prove the behavior.

### Email-specific intake routing

Email Intake performs work beyond PDF semantic parsing: thread routing, broker-resolution signals, duplicate-content checks, QR extraction, review persistence, and explicit operator actions. Those are **intake responsibilities**, not a reason to fork the Rate Confirmation semantic parser.

### Explicit create-draft action

Attachment ingestion/review and operational Load creation remain separate. PDF intake may produce review evidence; creating a Load is an explicit product action.

---

## 5. Current gaps

| Gap | Current reality |
|---|---|
| **OCR execution** | Page classification / `requires_ocr` gating is implemented; an OCR provider and OCR execution path are **not implemented**. |
| **Load Lab parser drift** | Lab still contains older proving-pipeline semantics and diagnostics that are intentionally not the production Rate Confirmation v2 brain. Lab docs must not call that pipeline the current product parser. |
| **General document classification / relevance** | Rate Confirmation is the first production profile. A generalized cross-module relevance/classification layer for arbitrary Load/Fuel/Toll documents is an architecture goal, not a claim about this shipped slice. |
| **Persisted product parse runs / versions** | Load Lab persists run/version/debug evidence. The synchronous Load Page parse endpoint is still hydration-oriented rather than a persisted parse-job/audit model. |
| **Async parse job** | The Load Page request remains synchronous in this snapshot; async job + polling is still design-only. |
| **Multi-document candidate merge** | [`MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md`](./MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md) remains a future design for grouping/merging multiple source documents. |
| **Lab cleanup debt** | [`LoadLabCleaner.md`](./LoadLabCleaner.md) remains the ledger for temporary/historical Lab bridges and needs periodic re-audit against parser v2. |

---

## 6. Direction of record

1. **Rate Confirmation v2 is the current product parser.** Do not revive the diagnostics-driven production path.
2. **LoadWorkspaceForm is the production load form.** Parse output hydrates that product surface.
3. **Load Lab is proving/debug/regression infrastructure.** It may compare ideas, but it does not define production parser truth.
4. **Email Intake may add routing/review logic around the product parser**, but should not grow a competing Rate Confirmation semantic brain.
5. **OCR, broader document classification/relevance, persisted parse-job execution, and multi-document merging remain separate future slices.**
6. When docs conflict, prefer current code + Shared Parsing Architecture + the Rate Confirmation parser design over April-era Lab pipeline reports.

---

## 7. Quick code index

| Area | Key files |
|---|---|
| Public product parser | `app/services/load_document_product_parser.py` |
| Rate Confirmation v2 | `app/services/load_document_parse_rate_con.py`, `load_parser_openai_handoff_v2.py`, `load_parser_rate_con_field_rules.py`, `load_parser_tenant_identity_exclusion.py`, `load_parser_mechanical_validation.py` |
| Acquisition | `app/services/pdf_text_extract.py`, `app/services/load_parser_pdf_acquisition.py` |
| Load Page parse route | `app/routers/loads.py`, `app/services/load_document_parse_orchestrator.py` |
| Production Load form / hydration | `apps/web/src/pages/LoadWorkspacePage.tsx`, `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx`, `apps/web/src/loadWorkspace/applyLoadDocumentParseResponse.ts` |
| Email PDF intake | `app/services/email_engine/intake_service.py`, `app/services/email_intake_pdf.py`, email review services |
| Load Lab | `app/routers/load_lab.py`, `app/services/load_lab.py`, `app/services/load_lab_semantic.py`, `app/models/load_lab.py`, `apps/web/src/pages/LoadLabPage.tsx` |
