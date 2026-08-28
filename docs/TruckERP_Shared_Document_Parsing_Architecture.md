# TruckERP — Shared Document Parsing Architecture

**Status:** Architecture lock (Rate Confirmation is the first production profile)  
**Scope:** Reusable document acquisition + semantic parsing across TruckERP modules  
**Date:** 2026-08-27  

**Related detailed design (do not replace):**  
[`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) — Rate Confirmation profile, field rules, and product-field contracts.

---

## 1. Purpose

TruckERP needs one **shared** way to turn unstructured documents into schema-valid JSON, without each module inventing its own PDF → OpenAI → repair stack.

This document defines:

1. **Pipeline 1 — Shared Document Acquisition** (text only; no business meaning)
2. **Pipeline 2 — Shared Semantic Parsing** (OpenAI + mechanical validation)
3. **Calling-module ownership** (profile, rules, schema, post-parse business logic)

Fuel / Toll / Load all consume the same pipelines. They do **not** share business reconciliation or posting rules.

---

## 2. Two-pipeline architecture

### Pipeline 1 — Shared Document Acquisition

**Purpose:** Convert an uploaded document into normalized page-separated text without understanding business meaning.

```text
PDF / image / attachment
        ↓
embedded text extraction
        ↓
classify each page
        ↓
embedded_text OR ocr_required
        ↓
OCR only where required  (NOT implemented yet)
        ↓
normalized pages[]
```

Acquisition **must not** determine:

* broker / carrier / fuel vendor / toll authority
* rate / load reference / transaction meaning
* stop role / business field mapping

It only produces:

* page-separated text (usable pages)
* mechanical metadata (`pdf_type`, `requires_ocr`, per-page `source`, metrics, warnings)

#### Current Slice 3A implementation

| Piece | Module | Status |
| ----- | ------ | ------ |
| Embedded extract | `app/services/pdf_text_extract.py` | Live |
| Page usability classify | `app/services/load_parser_pdf_acquisition.py` (`acquire_load_parser_pdf_pages`) | Complete (Slice 3A) |
| OCR provider | — | **Not implemented** |
| OCR provider lock | — | **Not locked** |

AWS Textract was investigated and recommended in prior inspection work, but it is **not** implemented and is **not** an architectural requirement of this document. Provider choice remains open until an OCR slice is approved.

When `requires_ocr` is true and OCR is unavailable, callers must **not** send blank/garbage pages into OpenAI and must **not** fall back to legacy semantic diagnostics.

---

### Pipeline 2 — Shared Semantic Parsing

```text
normalized pages[]
+
parser profile
+
profile-specific field rules
+
module-owned output schema
+
optional module context/exclusions
        ↓
OpenAI semantic reasoning
        ↓
schema-valid JSON
        ↓
mechanical validation
        ↓
return canonical JSON to requesting module
```

**Boundary:**

| Owner | Responsibility |
| ----- | -------------- |
| **OpenAI** | Semantic interpretation (who is broker, which id is primary load ref, stop roles, rate meaning, etc.) |
| **Server** | Mechanical validation only (shape, tenant-exclusion exact matches, numeric/date sanity, weak literal presence, leak stripping) |

There must be **no second semantic parser** on the server (no diagnostics-driven broker/contact/reference/rate/stop repair competing with the model).

---

## 3. Calling module owns

Each business module owns:

* parser **profile** name
* semantic field definitions / **field_rules**
* **output JSON schema**
* module-specific **context / exclusions**
* **business processing** after parse (hydrate UI, reconcile, post)

### Load / Rate Confirmation

Load module provides:

* `profile = rate_confirmation`
* Rate Confirmation field rules (`load_parser_rate_con_field_rules`)
* Load output schema (`ParseDocumentSemanticModelOutput` → `LoadDocumentParseResponse`)
* `tenant_identity_exclusion` (carrier/tenant company identity)

Shared parser returns Load parser JSON. Load module hydrates New Load.

### Fuel PDF

```text
Fuel PDF
→ shared acquisition
→ shared semantic parser(profile=fuel)
→ Fuel JSON
→ Fuel module
```

Example: BVD (or other vendor) fuel statement PDF upload.

### Fuel API

Structured trusted API data does **not** need OpenAI by default:

```text
BVD API JSON
→ Fuel module normalization/validation
→ Fuel business processing
```

Use shared semantic parsing only when unstructured/semi-structured document interpretation is required.

### Toll PDF

```text
Toll PDF
→ shared acquisition
→ toll profile/schema
→ OpenAI
→ Toll JSON
→ Toll module
```

### Toll API

```text
Toll API JSON
→ Toll module directly
```

---

## 4. Shared parser owns

Shared responsibilities:

* document acquisition
* embedded text extraction
* OCR orchestration when implemented
* page normalization
* OpenAI request transport
* generic profile handoff envelope
* response schema enforcement
* generic mechanical validation framework
* safe error / warning handling

Shared parser must **not** own:

* Load / Fuel / Toll business logic
* accounting posting
* broker selection rules outside profile instructions
* fuel or toll reconciliation

---

## 5. Rate Confirmation — first production profile

Rate Confirmation is the **first** production profile for this architecture.

| Slice | Status |
| ----- | ------ |
| Slice 1 — tenant identity exclusion | Complete |
| Slice 1B — in-process TTL cache + invalidate on profile save | Complete |
| Slice 2 — field rules + OpenAI handoff v2 | Complete |
| Slice 3A — PDF acquisition classifier | Complete |
| OCR | Not implemented |
| Mechanical post-model validator | Complete |
| Validator unit tests | 35 passing |
| Armstrong offline validation | PASS |
| J.B. Hunt offline validation | PASS |
| TQL original rate-con PDF | Unavailable (not freeze evidence) |

**Production cutover target path:**

```text
POST /api/v1/loads/parse-document
  → acquire_load_parser_pdf_pages()
  → if requires_ocr: controlled OCR-required response (no OpenAI; no legacy diagnostics)
  → get_load_parser_tenant_identity_exclusion()
  → rate_confirmation field rules + v2 handoff
  → OpenAI (ParseDocumentSemanticModelOutput)
  → map → LoadDocumentParseResponse
  → apply_load_parser_mechanical_validation()
  → return to New Load UI
```

Forbidden on the Rate Confirmation production path:

* `PRODUCT_PARSE_DIAGNOSTICS`
* `broker_party` / `carrier_party` / `role_hint`
* ranked reference candidates
* `financial_hints` / `route_stop_hints`
* semantic contact / reference / rate repair
* semantic stop reconstruction

---

## 6. Naming note

Several current modules still carry `load_parser_*` prefixes because Rate Confirmation was the first consumer. Functionally they already separate:

* acquisition (`load_parser_pdf_acquisition`) — reusable
* mechanical validation (`load_parser_mechanical_validation`) — reusable pattern
* tenant exclusion / field rules / handoff — Load-profile-specific today

Broad renames are **not** required for cutover; future Fuel/Toll profiles should add profile packages rather than renaming for aesthetics alone.
