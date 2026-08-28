# TruckERP — Shared Document Parsing Architecture

**Status:** **ARCHITECTURE LOCK — Rate Confirmation v2 is the first shipped production profile.**  
**Scope:** Reusable document acquisition + semantic parsing boundaries across TruckERP modules.  
**Date:** 2026-08-27; current-state refresh 2026-08-28.

**Related current docs:**

- [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) — implemented Rate Confirmation profile, field rules, tenant exclusion, and product output contract.
- [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — factual current route / integration map.

---

## 1. Purpose

TruckERP needs one shared boundary for turning unstructured documents into schema-valid JSON without every business module inventing its own PDF → OpenAI → semantic-repair stack.

This architecture separates:

1. **Shared Document Acquisition** — obtain normalized page-separated evidence without business meaning.
2. **Shared Semantic Parsing** — profile/schema/rules + OpenAI semantic interpretation + mechanical validation.
3. **Calling-module ownership** — module-specific profile, schema, context/exclusions, hydration/reconciliation/posting behavior.

Rate Confirmation is the first shipped production profile. Fuel, Toll, and other document profiles are **intended future consumers of the same boundaries**; this document does not claim those profiles are already implemented.

---

## 2. Pipeline 1 — Shared Document Acquisition

**Purpose:** Convert an uploaded document into normalized page-separated text and mechanical acquisition metadata without assigning business meaning.

```text
PDF / image / attachment
        ↓
embedded text extraction
        ↓
classify each page mechanically
        ↓
embedded_text OR ocr_required
        ↓
OCR only where required  (NOT implemented yet)
        ↓
normalized pages[]
```

Acquisition must **not** decide:

- broker / carrier / fuel vendor / toll authority
- rate / load reference / transaction meaning
- stop role / business field mapping

It may produce:

- page-separated text for usable pages
- mechanical metadata such as `pdf_type`, `requires_ocr`, per-page `source`, metrics, and warnings

### Current Rate Confirmation acquisition implementation

| Piece | Module | Status |
|---|---|---|
| Embedded extraction | `app/services/pdf_text_extract.py` | Live |
| Page usability classification | `app/services/load_parser_pdf_acquisition.py` (`acquire_load_parser_pdf_pages`) | Complete |
| OCR provider / execution | — | **Not implemented** |
| OCR provider architecture lock | — | **Not locked** |

When `requires_ocr` is true and OCR is unavailable, the production Rate Confirmation parser must **not** send blank/garbage pages into OpenAI and must **not** fall back to legacy semantic diagnostics.

---

## 3. Pipeline 2 — Shared Semantic Parsing

```text
normalized pages[]
+
parser profile
+
profile-specific field_rules
+
module-owned output schema
+
optional module context / exclusions
        ↓
OpenAI semantic interpretation
        ↓
schema-valid JSON
        ↓
mechanical validation
        ↓
canonical parser JSON returned to requesting module
```

### Ownership boundary

| Owner | Responsibility |
|---|---|
| **OpenAI / semantic model** | Business interpretation within the supplied profile/rules: party roles, primary ids, stop meaning, rate meaning, etc. |
| **Server mechanical layer** | Shape/schema cleanup, exact/normalized exclusions, finite numeric/date/sequence checks, weak literal-presence warnings, leak stripping, safe errors |

There must be **no second semantic parser on the server** competing with the model through diagnostics-driven broker/contact/reference/rate/stop ranking and repair.

---

## 4. Calling module owns

Each business module owns:

- parser **profile** name
- semantic **field_rules**
- module-owned **output schema**
- module-specific **context / exclusions**
- business processing after parse: hydrate UI, reconcile, review, post, etc.

### Load / Rate Confirmation

The Load module provides:

- `profile = rate_confirmation`
- frozen Rate Confirmation field rules (`load_parser_rate_con_field_rules`)
- output schema (`ParseDocumentSemanticModelOutput` → `LoadDocumentParseResponse`)
- `tenant_identity_exclusion` derived at runtime from the authenticated tenant/company profile

The parser returns Load parser JSON. The Load module hydrates the production Load Workspace; the parse DTO is not itself the persisted Load row.

### Future Fuel / Toll document profiles

Unstructured Fuel or Toll documents may use the same acquisition + semantic boundaries with their **own** profile, field rules, output schema, exclusions/context, and post-parse business logic.

Structured trusted API payloads do **not** require OpenAI by default; they can flow directly through module-owned normalization/validation.

---

## 5. Shared parser owns

Shared responsibilities:

- document acquisition primitives
- embedded text extraction
- OCR orchestration when implemented
- page normalization
- OpenAI request transport / common envelope
- response schema enforcement
- generic mechanical validation patterns
- safe error/warning handling

Shared parsing must **not** own:

- Load / Fuel / Toll business posting logic
- accounting reconciliation
- broker-specific product decisions outside the active profile/rules
- fuel/toll reconciliation rules
- UI save/apply policy

---

## 6. Rate Confirmation — current production profile

Rate Confirmation is the first shipped production profile for this architecture.

| Slice | Status |
|---|---|
| Tenant identity exclusion | Complete |
| In-process TTL cache + profile-save invalidation | Complete |
| Frozen field rules + OpenAI handoff v2 | Complete |
| PDF acquisition classifier | Complete |
| OCR | **Not implemented** |
| Mechanical post-model validator | Complete |
| Product cutover | **Shipped on inspection snapshot (`5498e6c4`)** |

### Current production path

```text
POST /api/v1/loads/parse-document
  → public load_document_product_parser
  → acquire_load_parser_pdf_pages()
  → if requires_ocr: controlled OCR-required response
       (no OpenAI; no legacy diagnostics)
  → get_load_parser_tenant_identity_exclusion()
  → Rate Confirmation field_rules + v2 handoff + page text
  → OpenAI (ParseDocumentSemanticModelOutput)
  → map → LoadDocumentParseResponse
  → apply_load_parser_mechanical_validation()
  → production Load Workspace hydration
```

Forbidden on the Rate Confirmation production path:

- `PRODUCT_PARSE_DIAGNOSTICS`
- `broker_party` / `carrier_party` / `role_hint`
- ranked semantic reference/contact candidates as model input
- `financial_hints` / `route_stop_hints`
- post-model semantic broker/contact/reference/rate repair
- competing semantic stop reconstruction

---

## 7. Durable safety rules for future shared expansion

These rules are retained from earlier PDF-pipeline design work because they remain useful beyond the first Rate Confirmation slice. They are **architecture principles**, not claims that every generic stage is already implemented.

1. **File sanity before expensive work.** Validate supported type/shape before OCR/model calls.
2. **Fingerprint/dedupe where the caller persists documents/runs.** Repeated bytes should be identifiable and reusable according to product policy; dedupe is not a reason to merge unrelated business records silently.
3. **Readability before semantics.** Digital PDF does not automatically mean usable evidence. Weak/scanned pages must be classified before model invocation.
4. **OCR must feed the same downstream profile/schema.** OCR is acquisition, not a separate business extractor.
5. **Classification/relevance before aggressive hydration when multiple document types are accepted.** An irrelevant certificate/invoice/etc. should not hydrate Rate Confirmation fields merely because text exists.
6. **Unknown is better than wrong.** Unsupported or ambiguous fields should remain null/unknown and surface warnings/review signals rather than be invented.
7. **No silent overwrite of trusted/user-confirmed values.** Applying parse output to persisted business records is a calling-module/product decision and must respect evidence strength and operator intent.
8. **Contradictions push toward review.** Competing identifiers, rates, parties, or stop evidence should be exposed rather than silently collapsed by a hidden heuristic.
9. **Version/evidence retention when parse runs are persisted.** Persisted evaluation/production-run models should record parser/schema/prompt/model/acquisition versions and enough evidence/warnings to reproduce why a value was proposed.
10. **One semantic owner per profile.** Deterministic code may validate mechanically, but it must not become a second hidden semantic brain.

### What Rate Confirmation v2 currently implements from this list

Implemented now: file/PDF sanity at the route, page readability classification, one downstream schema, model-owned semantics, mechanical validation, unknown/controlled OCR-required handling, and tenant-exclusion safety.

Still future/generalized: OCR execution, broad multi-document classification/relevance, a universal persisted parse-run/audit model for product routes, and generalized dedupe/reuse across all document entry points.

---

## 8. Naming note

Several modules still carry `load_parser_*` prefixes because Rate Confirmation was the first consumer. Functionally they already separate:

- acquisition (`load_parser_pdf_acquisition`) — reusable primitive/pattern
- mechanical validation (`load_parser_mechanical_validation`) — reusable pattern
- tenant exclusion / field rules / handoff — Rate Confirmation profile-specific today

Broad renames are not required merely for aesthetics. Future profiles should add clear profile packages/contracts rather than forcing a risky rename during feature work.

---

## 9. Documentation precedence

For current parser work, use this order:

1. Current code on the inspected branch.
2. This Shared Document Parsing Architecture lock.
3. `TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md` for the Rate Confirmation profile contract.
4. `CURRENT_PDF_LOAD_PATHS_AND_GAPS.md` for route/integration reality.
5. Load Lab documents only for proving/debug history and Lab-specific mechanics.

`PDF_LOAD_PIPELINE.md` is retained as a **superseded historical target-architecture record**. Its durable safety rules have been consolidated into this document; it must not override the shipped v2 architecture.
