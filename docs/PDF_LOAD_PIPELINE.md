# PDF load pipeline — target architecture

**Scope:** This document describes the **approved future** pipeline for load-related PDFs and derived documents. It is **design and architecture only** (the target contract and ordering of stages).

**Out of scope here:** Full specification of today’s production code paths. For a **factual map** of current routes and parsers (workspace, inbox, Load Lab v1, etc.), see [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md).

**Related:**

- [`LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`](./LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md) — isolated rollout surface, persistence, promote, audit.
- [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md) — where OpenAI fits when the semantic layer is implemented.
- [`LoadLabCleaner.md`](./LoadLabCleaner.md) — temporary bridges and cleanup ledger for Load Lab work.

---

## 1. Goal

TruckERP must turn heterogeneous broker/carrier/customs PDFs into **one canonical, TruckERP-owned JSON** contract suitable for validation, review, and apply decisions.

The target system must **not** rely on broker-specific labels or **global regex alone** as the final semantic layer.

---

## 2. Core architectural decision

| Layer | Role |
|--------|------|
| **Primary extraction brain** | OpenAI (or equivalent) **schema-constrained structured output** mapped to TruckERP **canonical JSON**. |
| **Fallback acquisition** | **OCR** (e.g. AWS Textract–class) when text is weak, scanned, or layout-dependent. |
| **Final semantics** | Always converge on the **same** canonical JSON contract — OCR supplies **text/layout evidence**, not a parallel ad hoc schema. |

**Rule:** OCR is **not** the final business extractor by itself; it feeds the same downstream mapping and gates as the digital text path.

---

## 3. Approved pipeline (ordered)

1. **File intake** — Accept upload; record metadata, tenant/source context, size, MIME; bind to thread/load/workspace context as applicable.
2. **Fingerprint / dedupe gate** — Content hash (and logical keys); skip or short-circuit duplicate work; surface duplicate awareness to operators when relevant.
3. **File type sanity gate** — PDF vs image vs unsupported; reject malformed inputs early with clear feedback.
4. **Readability gate** — After initial text pull: classify text usability (strong digital text vs weak vs scanned/mixed).
5. **Acquisition branch** — **Digital text path** vs **OCR path** (weak/scanned); both feed the same next stage.
6. **Normalized document package** — Single intermediate shape: metadata, method, per-page text, full text, structure hints (blocks/lines/tables where available), warnings.
7. **Document classification** — Coarse type (e.g. rate confirmation, broker information sheet, customs, invoice/irrelevant, unknown) to drive field relevance and review rules.
8. **Relevance gate** — Decide if the document should influence **load** extraction at all (full / partial / none).
9. **AI schema mapping** — Map normalized evidence → **TruckERP canonical JSON** via schema-bound generation (not broker-native field names as the persistence contract).
10. **Deterministic validation** — Types, enums, dates, money, stop ordering, required pairs, impossible combinations — **schema-valid ≠ business-valid**.
11. **Confidence + contradiction gates** — Document-, group-, and field-level confidence; detect conflicts (e.g. identity vs MC/DOT, competing rates/refs, stop inconsistencies). Contradictions push toward **review**, not silent apply.
12. **Apply / review decision** — Outcomes such as auto-apply, apply-with-review, review-only, reject — with rules against overwriting trusted or user-confirmed values with weak evidence.
13. **Persist evidence and versions** — Store extraction method, schema/prompt/parser versions, confidence, warnings, contradiction flags, and traceable evidence where practical for audit and safe reparse.

---

## 4. Stage notes (expanded)

### File intake

Capture **provenance** (manual workspace, email thread upload, sync-derived attachment, etc.) so later gates and UI can explain **why** a package was produced.

### Fingerprint / dedupe gate

Reduces noise from the same bytes attached multiple times; supports linking to prior outcomes without re-running full extraction when policy allows.

### File type sanity gate

Stops unsupported types before expensive OCR or model calls.

### Readability gate

**Digital PDF ≠ usable text.** Layout extraction may yield garbage order or empty text; this gate chooses the acquisition branch and records warnings.

### Digital text path vs OCR path

Both branches **must** emit the **same normalized document package** shape so downstream classification and mapping do not fork by implementation.

### Normalized document package

The contract between **acquisition** and **semantic extraction**. Keeps one “document brain” input regardless of how text was obtained.

### Document classification + relevance gate

Prevents irrelevant PDFs (e.g. generic certificates, wrong doc type) from hydrating load fields; enables **document-type-aware** field expectations and operator messaging.

### AI schema mapping into TruckERP canonical JSON

This is the planned **primary semantic step**: structured output aligned to an internal schema, with explicit handling of unknowns and ambiguity.

### Deterministic validation + confidence / contradiction gates

Human-trust and system-safety layer **after** the model — not optional polish.

### Apply / review decision

Bridges extraction to product behavior: what may auto-fill, what is suggestion-only, what blocks save until acknowledged.

### Persist evidence and versions

Enables debugging (“why did this PDF set rate X?”), regression analysis on prompt/schema changes, and compliance-style audit trails.

---

## 5. Non-negotiable principles

- **One** canonical JSON output contract for loads (and explicit extensions for non-load doc types if needed).
- **Unknown is better than wrong** at the mapping layer.
- **No silent overwrite** of trusted or user-confirmed values with low-evidence extractions.
- **Relevance before hydration**; **classification before aggressive field fill** where possible.
- **Confidence and contradictions are first-class.**
- **Version and evidence** travel with results.

---

## 6. Pitfalls the target design avoids

- Assuming all digital PDFs yield ordered, complete plain text.
- Using **one global regex scan** of raw text as the **final** semantic source for broker PDFs.
- Letting **inbox** and **workspace** paths drift into **two incompatible “truths”** without a shared normalized package and mapping step.
- Returning **different JSON shapes** from OCR vs digital branches.
- Single global confidence scores with no contradiction handling.
- Unversioned prompt/schema changes in production debugging.

---

## 7. Current implementation footprint (Load Lab v1)

Load Lab is the **first shipped slice** aligned with this document’s **persistence, versioning, and review** intent. It does **not** yet implement the full target pipeline (no OpenAI semantic mapping in production code; no OCR acquisition path).

| Pipeline stage (this doc) | Load Lab v1 (approx.) |
|----------------------------|------------------------|
| 1–2 Intake + fingerprint / dedupe | Yes — upload, SHA-256, optional reuse of prior run when version pins match. |
| 3–4 File type + readability | Partial — PDF magic check; weak/image-only → `ocr_required` / `failed` without OCR execution. |
| 5–6 Acquisition + normalized package | Partial — digital text via existing PDF text extraction; `normalized_package` JSON persisted. |
| 7–8 Classification + relevance | Stub — e.g. `classification_label` / `relevance` heuristics; not doc-type ML. |
| 9 AI schema mapping | **Not yet** — regex-backed `parse_response` only; `ai_model_output` reserved. |
| 10–11 Validation + confidence / contradictions | Partial — Pydantic validation of parse response; limited contradiction model. |
| 12–13 Apply decision + evidence | Partial — explicit **promote** / **reject**; promote audit rows; best-effort `audit_events`. |

**Cleanup / debt** for shortcuts inside Load Lab: [`LoadLabCleaner.md`](./LoadLabCleaner.md).

---

## 8. Implementation stance

**Report-first / investigation-first:** This pipeline remains the **direction of record**. Further shipping should close gaps row-by-row in §7 (OpenAI mapping, OCR, classification, field-level promote, etc.) with **explicit cutover** from today’s split routes — **without** treating `load_document_parse.py` or ad hoc inbox regex as the long-term **extraction brain**.

**Operational rule:** New semantic extraction work should land in **Load Lab first** until quality and audit gates justify wiring the same contract into the main load workspace or intake automation.
