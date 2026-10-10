# Current PDF load paths and gaps

**Status:** **CURRENT REALITY MAP — verified 2026-08-28 against `inspect/current-working-state-2026-08-28`.**  
**Scope:** Current Load / Rate Confirmation PDF entry points and their relationship to the shared Document Parser, Email Intake, and Load Lab.  
**Product rule:** **Load Lab is proving/debug/regression, not the product Load Page. `LoadWorkspaceForm` is the production editable load form.**

**Parser architecture rule:** TruckERP has **one shared Document Parser pipeline**. Rate Confirmation is its first shipped production profile; future Fuel/Toll document profiles attach to that same engine rather than creating separate end-to-end pipelines.

**Current parser truth:**

- [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md)
- [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md)
- [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md)

Earlier pipeline/rollout records are retained under [`archive/`](./archive/README.md); they are not current parser implementation authority.

---

## 1. Current production parser path

The canonical public product parser entrypoint for Load / Rate Confirmation PDFs is:

```text
app/services/load_document_product_parser.py
  → parse_pdf_bytes_to_load_document_response(...)
  → Rate Confirmation v2 implementation/profile
```

Current Rate Confirmation flow:

```text
PDF
→ page acquisition / embedded-text usability classification
→ OCR-required gate when needed
→ tenant_identity_exclusion
+ frozen Rate Confirmation field_rules
+ page-separated text
→ OpenAI semantic mapping
→ mechanical validation
→ LoadDocumentParseResponse
```

The product path does **not** use `PRODUCT_PARSE_DIAGNOSTICS`, `broker_party`, `carrier_party`, `role_hint`, ranked semantic candidate packets, or the old diagnostics-driven semantic repair stack.

---

## 2. Current route / ownership table

| Flow | Parser / service | Persistence / effect | Product meaning |
|---|---|---|---|
| **Load Page PDF parse** — `POST /api/v1/loads/parse-document` | `parse_load_workspace_document_orchestrated(...)` → public product parser → Rate Confirmation profile | Endpoint does not itself create/update a Load; result hydrates client workspace draft state | **Production Load Page parse path** |
| **Email Intake PDF upload / recompute** | `apply_email_pdf_intake(...)` → public product parser for review snapshot, plus intake-specific broker resolution / QR / duplicate checks | Persists intake/review state; **no automatic Load creation** inside PDF intake | **Production intake review path using the same Rate Confirmation profile for PDF semantics** |
| **Create draft Load from intake review** | Explicit email-thread action using review/broker-resolution state | Creates a Load only after explicit operator action | **Separate product action; not the parser itself** |
| **Load Lab upload / semantic evaluation** | Lab-specific services/run models | Persists Lab runs/debug/review state | **Proving/regression surface; not production parser truth** |
| **Async Load Page parse job** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) | Not implemented | **Future transport; does not redefine parser semantics** |

---

## 3. What is shared now

### Public product parser

Feature code that needs production PDF → `LoadDocumentParseResponse` semantics uses the public product parser rather than adding another public semantic entrypoint.

### Output/hydration contract

The Rate Confirmation profile returns `LoadDocumentParseResponse` / `LoadParseExtractedFields`. The production Load Page maps that DTO into workspace draft state; the parse DTO is not the persisted `Load` row.

### Acquisition boundary

Per-page text usability is classified before semantic parsing. OCR-required pages do not fall back to the legacy diagnostics parser.

---

## 4. What remains intentionally separate

### Load Lab

Lab can keep historical diagnostics, comparison modes, run metadata, JSON panels, and evaluation tools. The rule is:

> **Do not fix the product parser by making Load Lab the product. Fix the shared Document Parser/profile, then use Lab to prove the behavior.**

### Email Intake

Email Intake owns routing, broker-resolution signals, duplicate-content checks, QR extraction, review persistence, and explicit operator actions around the parser. Those concerns do not justify a second Rate Confirmation semantic engine.

### Future Fuel / Toll

Fuel and Toll document parsing should attach new profiles to the same shared Document Parser engine. Fuel/Toll reconciliation and posting remain their module-owned business logic. Trusted structured Fuel/Toll API JSON may bypass document parsing.

---

## 5. Current gaps

| Gap | Current reality |
|---|---|
| **OCR execution** | Usability/`requires_ocr` gating exists; OCR provider/execution does not. |
| **General document classification/relevance** | Rate Confirmation is the first production profile; generalized arbitrary-document classification/relevance is future. |
| **Fuel/Toll document profiles** | Architecture is locked; implementation is future unless separately shipped. |
| **Persisted product parse runs** | Lab persists runs/version/debug evidence; the synchronous Load Page route remains hydration-oriented. |
| **Async parse job** | Design-only in this snapshot. |
| **Multi-document candidate merge** | [`MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md`](./MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md) remains future design. |
| **Lab cleanup debt** | [`LoadLabCleaner.md`](./LoadLabCleaner.md) remains the cleanup ledger and must be re-audited against v2/shared-parser truth. |

---

## 6. Direction of record

1. **One Document Parser engine, many profiles.**
2. **Rate Confirmation v2 is the first shipped production profile.**
3. **LoadWorkspaceForm is the production Load form.**
4. **Load Lab is proving/debug/regression infrastructure.**
5. **Email Intake can wrap routing/review around the product parser but must not create a competing semantic brain.**
6. **Fuel/Toll document parsing attaches profiles to the same engine.**
7. **OCR, broader classification/relevance, persisted parse-job execution, and multi-document merging are separate future slices.**

---

## 7. Quick code index

| Area | Key files |
|---|---|
| Public Load product parser adapter | `app/services/load_document_product_parser.py` |
| Rate Confirmation profile/implementation | `app/services/load_document_parse_rate_con.py`, `load_parser_openai_handoff_v2.py`, `load_parser_rate_con_field_rules.py`, `load_parser_tenant_identity_exclusion.py`, `load_parser_mechanical_validation.py` |
| Acquisition | `app/services/pdf_text_extract.py`, `app/services/load_parser_pdf_acquisition.py` |
| Load Page route | `app/routers/loads.py`, `app/services/load_document_parse_orchestrator.py` |
| Load form/hydration | `LoadWorkspacePage.tsx`, `LoadWorkspaceForm.tsx`, `applyLoadDocumentParseResponse.ts` |
| Email PDF intake | `app/services/email_engine/intake_service.py`, `app/services/email_intake_pdf.py` |
| Load Lab | `app/routers/load_lab.py`, `app/services/load_lab.py`, `app/services/load_lab_semantic.py`, `app/models/load_lab.py`, `LoadLabPage.tsx` |
