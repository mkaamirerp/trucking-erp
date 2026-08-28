# PDF load pipeline — historical target architecture

**Status:** **SUPERSEDED / HISTORICAL TARGET-ARCHITECTURE RECORD.**  
**Current architecture:** [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md) + [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md).  
**Current route reality:** [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md).  
**2026-08-28 consolidation:** durable rules from this document — file sanity/dedupe, readability before semantics, OCR converging on the same profile/schema, relevance before aggressive hydration, unknown-over-wrong, no silent overwrite, contradiction/review gates, and version/evidence retention — were consolidated into the Shared Document Parsing Architecture.

The body below is retained as the earlier target design and rollout rationale. Statements such as “Load Lab first,” “OpenAI not yet implemented,” or “direction of record” describe the **pre–Rate Confirmation v2** phase and must not override the current architecture/code.

---

## 1. Historical goal

TruckERP must turn heterogeneous broker/carrier/customs PDFs into a TruckERP-owned structured contract suitable for validation, review, and apply decisions.

The target system must not rely on broker-specific labels or global regex alone as the final semantic layer.

---

## 2. Historical core architectural decision

| Layer | Role |
|---|---|
| **Primary extraction brain** | OpenAI (or equivalent) schema-constrained structured output mapped to TruckERP-owned JSON. |
| **Fallback acquisition** | OCR when text is weak, scanned, or layout-dependent. |
| **Final semantics** | Digital text and OCR converge on the same downstream profile/schema; OCR supplies evidence, not a parallel business schema. |

**Durable rule retained:** OCR is acquisition, not the final business extractor.

---

## 3. Historical ordered pipeline

1. **File intake** — accept upload; record metadata, tenant/source context, size, MIME, and relevant product context.
2. **Fingerprint / dedupe gate** — content hash and logical duplicate awareness.
3. **File type sanity gate** — PDF vs image vs unsupported; reject malformed inputs early.
4. **Readability gate** — classify usable digital text vs weak/scanned/mixed evidence.
5. **Acquisition branch** — digital extraction vs OCR; both feed the same downstream shape.
6. **Normalized document package** — metadata, method, per-page text, warnings, and structure hints where available.
7. **Document classification** — coarse document type to drive relevance and field expectations.
8. **Relevance gate** — decide whether the document should influence Load extraction.
9. **AI schema mapping** — evidence → TruckERP-owned structured output through schema-bound generation.
10. **Deterministic validation** — types, enums, dates, money, stop ordering, required pairs, impossible combinations.
11. **Confidence + contradiction gates** — conflicting ids/rates/parties/stops push toward review rather than silent apply.
12. **Apply / review decision** — auto-apply, review-only, reject, etc., with no silent overwrite of trusted values.
13. **Persist evidence and versions** — parser/schema/prompt/model/acquisition versions, warnings, confidence, contradictions, traceable evidence where practical.

The newer Shared Document Parsing Architecture retains the durable safety rules above while intentionally using a simpler first production profile for Rate Confirmation v2.

---

## 4. Historical stage notes

### File intake / provenance

Capture whether evidence came from manual workspace upload, email attachment, sync-derived document, or another source so operators can understand why a parse/review result exists.

### Fingerprint / dedupe

Repeated bytes should be identifiable. Reuse policy is a product decision and must not silently merge unrelated business records.

### File type / readability

Digital PDF does not guarantee usable ordered text. Weak/scanned evidence should be identified before expensive semantic processing.

### Digital vs OCR

Both acquisition branches must converge on the same semantic profile/schema. OCR does not create a separate business interpretation stack.

### Classification / relevance

When many document types are accepted, irrelevant documents should not hydrate aggressive Load fields simply because text exists.

### AI mapping

Semantic output should be schema-constrained and TruckERP-owned rather than persisting broker-native labels as the product contract.

### Mechanical validation / contradiction gates

Schema-valid is not automatically business-valid. Ambiguity and conflicting evidence should surface as review rather than being hidden by a deterministic guess.

### Apply / review

Extraction and persistence are separate decisions. Trusted/user-confirmed values must not be silently overwritten by weak candidate data.

### Evidence / versions

Persisted parse runs should carry enough version/evidence metadata to explain and reproduce why a value was proposed.

---

## 5. Durable principles retained in the current architecture

- Unknown is better than wrong.
- No silent overwrite of trusted/user-confirmed values.
- Readability before semantics.
- OCR and digital acquisition converge on one semantic profile/schema.
- Relevance before aggressive hydration when multiple doc types are accepted.
- Confidence/contradictions should drive review.
- Persisted runs should retain versions/evidence.
- Do not use one global regex scan as the final semantic brain.

These principles now live in `TruckERP_Shared_Document_Parsing_Architecture.md`; maintain them there going forward.

---

## 6. Historical pitfalls this design was meant to avoid

- Assuming all digital PDFs yield ordered/complete text.
- Using one global regex scan as the final semantic source.
- Letting inbox/workspace/Lab grow incompatible business semantics.
- Returning different business schemas from OCR vs digital branches.
- Single global confidence without contradiction handling.
- Unversioned prompt/schema changes that cannot be debugged.

---

## 7. Historical Load Lab v1 footprint

At the time this document was active, Load Lab was the first proving slice for persistence/versioning/review ideas. It did not represent the final product parser and its implementation reports are now historical.

The original approximation was:

| Stage | Historical Load Lab state |
|---|---|
| Intake + fingerprint | Upload + SHA-256 + optional prior-run reuse |
| File type + readability | Partial PDF/weak-text checks |
| Acquisition + normalized package | Digital text + persisted Lab normalized package |
| Classification + relevance | Stub / heuristic |
| AI mapping | Initially absent; later added in Lab experiments |
| Validation/confidence | Partial / evolving |
| Apply/review + evidence | Lab-specific review/promote/audit tooling |

Current production Rate Confirmation semantics no longer depend on this Lab evolution path.

---

## 8. Historical implementation stance

The original rollout stance was investigation-first and Lab-first: prove new semantic behavior in an isolated surface before cutting it into the product Load Page.

That rollout history remains useful, but **it is no longer current parser authority**. Rate Confirmation v2 is now shipped on the product parser path. Future shared-parser work should start from the Shared Document Parsing Architecture and the current code rather than reopening this historical target document.
