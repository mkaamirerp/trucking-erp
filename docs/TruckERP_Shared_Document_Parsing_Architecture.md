# TruckERP — Shared Document Parsing Architecture

**Status:** **ARCHITECTURE LOCK — one shared Document Parser pipeline; Rate Confirmation v2 is the first shipped production profile.**  
**Scope:** Reusable document acquisition + semantic parsing across TruckERP.  
**Date:** 2026-08-27; current-state refresh 2026-08-28.

**Related current docs:**

- [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) — implemented Rate Confirmation profile contract.
- [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — factual current route/integration map.
- [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) — Load Lab vs production Load Page boundary.

---

## 1. Core lock: one parser pipeline, many document profiles

TruckERP has **one shared Document Parser engine/pipeline**. Business document types attach to that engine as **profiles/adapters**; they do not create competing end-to-end parser stacks.

```text
                    ┌─ Rate Confirmation profile
Document Parser ────┼─ Fuel document profile
(shared engine)     ├─ Toll document profile
                    ├─ Invoice / other future profiles
                    └─ ...
```

The shared engine owns acquisition, model transport, schema enforcement, mechanical validation patterns, and safe failure behavior. A document profile contributes the business-specific meaning needed for that document type.

**Do not build separate full pipelines such as `fuel_parser`, `toll_parser`, or another Load parser that each reinvent PDF acquisition → OpenAI → validation.** A profile/package may use a document-specific module name, but it must plug into the same shared parser boundary.

Rate Confirmation is the first shipped production profile. Fuel, Toll, and other profiles are future consumers unless their implementation is explicitly documented as shipped.

Structured trusted API data is different: Fuel/Toll API JSON can bypass document parsing and go directly through module-owned normalization/validation.

---

## 2. Shared pipeline

### Pipeline A — Document acquisition

```text
PDF / image / attachment
        ↓
file sanity
        ↓
embedded text extraction
        ↓
mechanical page usability classification
        ↓
embedded_text OR ocr_required
        ↓
OCR only where required (not implemented yet)
        ↓
normalized pages[] + mechanical metadata
```

Acquisition must not decide business meaning such as broker/carrier identity, fuel vendor meaning, toll authority meaning, rate, load reference, stop role, or accounting treatment.

Current reusable implementation/patterns include:

- `app/services/pdf_text_extract.py` — embedded extraction
- `app/services/load_parser_pdf_acquisition.py` — current Rate Confirmation page usability classifier
- OCR provider/execution — **not implemented / not locked**

When OCR is required and unavailable, callers must not send blank/garbage pages into the semantic model and must not fall back to an obsolete semantic diagnostics stack.

### Pipeline B — Semantic parsing

```text
normalized pages[]
+
document profile
+
profile field_rules
+
profile output schema
+
profile context / exclusions
        ↓
shared model transport
        ↓
semantic interpretation
        ↓
schema-valid JSON
        ↓
mechanical validation
        ↓
profile result returned to calling module
```

There is **one semantic owner per profile**. Deterministic server code can validate mechanically but must not become a second hidden semantic brain through candidate ranking or post-model business reinterpretation.

---

## 3. What a document profile owns

Each attached document profile owns only its document-specific contract:

- profile identifier/name
- semantic field definitions / `field_rules`
- output JSON schema
- profile-specific context and exclusions
- mapping/hydration into the calling module
- business processing after parse

Examples:

### Rate Confirmation profile — shipped

- `profile = rate_confirmation`
- frozen Rate Confirmation field rules
- `tenant_identity_exclusion`
- `ParseDocumentSemanticModelOutput` → `LoadDocumentParseResponse`
- Load Workspace hydration after parse

### Future Fuel document profile

A Fuel PDF/statement plugs into the same Document Parser engine with Fuel-owned field rules/schema/context, then returns Fuel JSON to the Fuel module. Fuel reconciliation/posting remains Fuel-module logic.

### Future Toll document profile

A Toll PDF/statement plugs into the same Document Parser engine with Toll-owned field rules/schema/context, then returns Toll JSON to the Toll module. Toll reconciliation/posting remains Toll-module logic.

A new profile must **not** fork the acquisition/model/validation pipeline merely because its business fields differ.

---

## 4. Shared Document Parser owns

The shared parser boundary owns:

- file/document acquisition primitives
- embedded text extraction
- OCR orchestration when implemented
- page normalization
- common model/OpenAI request transport and safe timeout/error handling
- profile handoff envelope
- response schema enforcement
- generic mechanical validation framework/patterns
- common leak/redaction/safety handling

The shared parser must not own:

- Load/Fuel/Toll posting or reconciliation
- accounting decisions
- broker-specific decisions outside the active Rate Confirmation profile
- UI save/apply policy
- dispatch/payroll/custody logic

---

## 5. Rate Confirmation v2 — first production profile

Current shipped path on the inspection snapshot:

```text
POST /api/v1/loads/parse-document
  → public load_document_product_parser
  → Rate Confirmation profile
  → acquire_load_parser_pdf_pages()
  → if requires_ocr: controlled OCR-required response
  → get_load_parser_tenant_identity_exclusion()
  → frozen Rate Confirmation field_rules + page text
  → OpenAI semantic mapping
  → LoadDocumentParseResponse
  → apply_load_parser_mechanical_validation()
  → LoadWorkspaceForm hydration
```

Implemented:

- tenant identity exclusion
- in-process TTL cache + profile-save invalidation
- frozen field rules + clean OpenAI handoff v2
- page usability classification
- mechanical post-model validation
- product cutover (`5498e6c4` on the inspection branch)

Not implemented:

- OCR provider/execution
- generalized arbitrary-document classification/relevance across all profiles
- Fuel/Toll document profiles unless separately shipped later

Forbidden on the Rate Confirmation production path:

- `PRODUCT_PARSE_DIAGNOSTICS`
- `broker_party` / `carrier_party` / `role_hint`
- ranked semantic candidate packets as model input
- diagnostics-driven post-model broker/contact/reference/rate repair
- a second semantic stop reconstruction engine

---

## 6. Durable safety principles for every profile

1. **File sanity before expensive work.**
2. **Fingerprint/dedupe where the caller persists documents/runs.** Dedupe must never silently merge unrelated business records.
3. **Readability before semantics.** Digital PDF does not automatically mean usable text.
4. **OCR feeds the same Document Parser/profile contract.** OCR is acquisition, not a separate business parser.
5. **Classification/relevance before aggressive hydration** when a surface accepts multiple document types.
6. **Unknown is better than wrong.** Ambiguous/unsupported values remain null/unknown with warnings/review signals.
7. **No silent overwrite of trusted or user-confirmed values.** Applying parser output is a calling-module/product decision.
8. **Contradictions push toward review.** Do not hide competing identifiers, rates, parties, or stop evidence behind a heuristic.
9. **Persist versions/evidence when parse runs are stored.** Record parser/profile/schema/prompt/model/acquisition versions plus enough evidence/warnings to reproduce outcomes.
10. **One semantic owner per profile.** Mechanical code validates; it does not compete with the semantic model.

---

## 7. Naming / module organization

Some existing modules still carry `load_parser_*` names because Rate Confirmation was the first consumer. That does **not** mean the target architecture is “one Load parser plus separate Fuel/Toll parsers.”

Target organization is conceptually:

```text
document_parser/                  # shared engine/pipeline
  acquisition
  model_transport
  validation
  profiles/
    rate_confirmation/
    fuel/                         # future
    toll/                         # future
```

A broad rename is not required during active feature work. The architectural boundary matters more than cosmetic filenames: new profiles must attach to the shared engine rather than duplicating it.

---

## 8. Load Lab boundary

Load Lab is a proving/debug/regression surface. It may retain persisted runs, experiment modes, historical diagnostics, or evaluation metadata, but it is **not** the shared Document Parser and it is **not** a second production Load Page.

Fix production semantics in the shared parser/profile, then use Lab to prove them.

---

## 9. Documentation precedence

For current document-parser work, use this order:

1. Current code on the inspected branch.
2. This Shared Document Parsing Architecture lock.
3. The active document profile design/contract (currently Rate Confirmation).
4. `CURRENT_PDF_LOAD_PATHS_AND_GAPS.md` for route/integration reality.
5. Load Lab evidence only for proving/debug history.

Earlier pipeline/rollout reports are retained under [`archive/`](./archive/README.md) after their durable rules are consolidated. They must not override this one-engine/many-profiles architecture.
