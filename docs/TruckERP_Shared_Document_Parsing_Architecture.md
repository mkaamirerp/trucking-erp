# TruckERP — Shared Document Platform Architecture

**Status:** **ARCHITECTURE LOCK — calling API chooses profile; profile selects capabilities; no document-type guessing.**  
**Scope:** Shared document **capabilities** + explicit **profiles**. Not a universal pipeline that always runs every capability.  
**Date:** 2026-08-27; current-state refresh 2026-09-01 (through PDF text capability ownership).

**Related current docs:**

- [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) — Rate Confirmation profile contract (frozen).
- [`TRUCKERP_DRIVER_LICENCE_PIPELINE.md`](./TRUCKERP_DRIVER_LICENCE_PIPELINE.md) — Driver Licence pipeline (frozen).
- [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — factual Load/PDF route map.
- [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) — Load Lab vs production Load Page boundary.

**Current runtime checkpoint:** `72917f4a70177ea9daf91074881fd096135934cb`. OpenAI transport and PDF **text extraction** ownership have moved into Document Platform; production callers are **not** rewired. The RateCon PDF acquisition classifier is **not** shared. See **Current state / resume anchor** below.

---

## Current state / resume anchor (through PDF text capability)

### Architecture rule

- The calling business API / module selects an **explicit profile**.
- Document Platform does **not** inspect bytes or content to decide whether a document is Rate Confirmation, Fuel, Toll, POD, Driver Licence, or any other future profile.
- The profile selects which capabilities execute, plus schema, rules, and context.
- Business posting and reconciliation remain **outside** Document Platform.

### Current implemented capability ownership

**OpenAI JSON-schema transport**

- Implementation: `app/document_platform/capabilities/openai/chat_json_schema.py`
- Compatibility shim: `app/services/openai_chat_json_schema.py`
- Production RateCon and Load Lab callers still import the old path. Caller rewiring has **not** started.
- Load-specific HTTP-400 fallback remains unchanged.

**PDF embedded-text extraction**

- Implementation owner: `app/document_platform/capabilities/pdf/text_extract.py`
- Public functions: `extract_text_and_pages_from_pdf_bytes`, `extract_text_from_pdf_bytes`
- Compatibility shim: `app/services/pdf_text_extract.py` (re-exports the same callable objects)
- Production callers (RateCon acquisition, Load Lab, email-intake hints) still import the old compatibility path. Caller rewiring has **not** started.

### PDF extraction contract (current locked mechanical behavior)

`extract_text_and_pages_from_pdf_bytes(data: bytes)` returns `(full_text, page_texts, warnings)`.

This is the **current PDF text capability contract**, not a universal business policy:

- `page_texts` remains in PDF page order (list index 0 = first page)
- empty / `None` page extraction becomes `""`; empty page slots are retained
- `full_text == "\n".join(page_texts)`
- per-page extraction failures preserve an empty slot
- page-error warning index is currently **zero-based** (`"Page {i} extract error: {TypeName}"`)
- no page markers; no page-number metadata; no whitespace normalization
- failures become warnings rather than being raised (missing pypdf, open error, per-page error)

Exact warning strings are test-locked in `tests/test_pdf_text_extract.py`.

`extract_text_from_pdf_bytes` returns `(full_text, warnings)` and drops `page_texts`.

### RateCon OpenAI page contract (distinct from joined full_text)

The Rate Confirmation OpenAI handoff does **not** use the extractor’s joined `full_text` as semantic input.

It uses **page-separated usable pages** `{page_number, text}` in the RateCon handoff JSON (`document.pages`). Joined `full_text` / response `raw_text` is a **separate** hydration representation.

### Acquisition classifier — not genericized

`app/services/load_parser_pdf_acquisition.py` remains **outside** the shared PDF capability.

It includes RateCon/Load-proven policy, not platform-generic rules:

- `MIN_ALPHANUMERIC_CHARS = 40`
- `MIN_WORD_LIKE_TOKENS = 5`
- page usability classification
- `digital_text` / `scanned_image` / `mixed`
- whole-document `requires_ocr=True` when **any** page lacks usable embedded text
- weak/unusable page text omitted from the semantic handoff (`text=""`; optional `weak_embedded_text` diagnostics only)

There is **not** sufficient evidence that Fuel, Toll, POD, or other PDF profiles should use those same thresholds or mixed-document blocking policy.

**Do not** move or generalize `load_parser_pdf_acquisition.py` yet.

### OCR boundary

There is **no** production mechanical OCR engine on the Rate Confirmation PDF path (no Tesseract, Textract, Document AI, EasyOCR, OCRmyPDF, or other engine in this path).

Acquisition may classify OCR as required. It does **not** perform OCR.

When RateCon `requires_ocr` is true, the semantic / OpenAI parse is **blocked** and a controlled `LoadDocumentParseResponse` is returned.

### Completed migration checkpoints

| Slice | SHA | What landed |
|---|---|---|
| 0 | `29bd4aea02a972d2bc4f60c8e79c0fd9074e37e1` | package/profile architecture boundary |
| 1A | `3f37829f83a58b02a30d9b94e08f0b87d58aa257` | OpenAI capability compatibility namespace |
| 1B | `cc5008d642ee2d4b5586f672d7413863e638696d` | callable identity compatibility test |
| 1C+1D | `2903f8f1713c3f8a8ec58785198dd64438531ca5` | physical OpenAI transport ownership move + shim + mock/test coverage repair |
| OpenAI docs | `11a227a8868dcad439d7c83598ec3da84da9b95c` | architecture anchor after OpenAI 1C+1D |
| PDF A | `4defce3ae3b61d317acd969aa626d034493c2258` | add PDF text capability namespace |
| PDF tests | `d7e34313f8f4b65087f0246d8f0dcc46948e18f8` | lock PDF text extraction behavior |
| PDF move | `754b173b34208837bd65bcf9c81d9644b534a36e` | move PDF text extraction capability |
| PDF docs | `72917f4a70177ea9daf91074881fd096135934cb` | correct PDF capability ownership note |

### Frozen Driver Licence profile composition

- Browser image normalization ceiling ≤ 2400
- Server OpenCV working copy ≤ 1544
- Existing four-corner confirmation authority
- Optional strict short-side repair
- Final warp 1000×631
- Original-first PDF417 decode
- AAMVA → driver intake
- Phone user confirmation
- No OpenAI
- No OCR in the live path
- Driver Licence module is **completed/frozen** unless a new defect arises
- Do **not** genericize DL OpenCV into the PDF capability

### Frozen Rate Confirmation profile composition

- Shared PDF **text** capability (via compatibility shim today)
- RateCon-owned usability / OCR-required **gate** (`load_parser_pdf_acquisition`)
- No mechanical OCR currently
- Tenant identity exclusion
- RateCon field rules / schema / page-separated OpenAI handoff
- Shared OpenAI transport
- Mechanical validation
- Workspace hydration response
- No Load creation / business posting inside Document Platform

### Future profiles

The shared PDF text capability is **available** for future profiles. It is **not** automatically mandatory.

Each profile (Fuel, Toll, POD, or other) decides whether it uses embedded PDF text, OCR, image processing, barcode, OpenAI, or other capabilities based on **actual** business/profile requirements. Do not create speculative empty Fuel / Toll / POD packages.

### Current migration boundary

- **Do not** generalize DL OpenCV into a universal geometry capability.
- PDF417 decode may later become a reusable capability; AAMVA / driver intake remains DL profile logic.
- **Do not** move `load_parser_pdf_acquisition.py` into shared capabilities yet.
- Do not create speculative empty Fuel / Toll / POD packages.
- Load Lab remains separate evaluation tooling.

### NEXT STEP / resume

**Current committed checkpoint:** `72917f4a70177ea9daf91074881fd096135934cb`

**Completed:** Document Platform skeleton; shared OpenAI transport ownership move + compatibility shim; PDF text capability namespace; PDF extractor behavior lock; PDF text implementation ownership move; old PDF service compatibility shim.

**Not started:** production caller rewiring to the new PDF path; `load_parser_pdf_acquisition` generalization; production OCR capability; Fuel / Toll / POD profile implementation.

**Recommended next decision:** **STOP** before moving `load_parser_pdf_acquisition.py` and gather evidence from the **next real profile** first.

Do not create speculative generic classifier code just because the PDF text extractor is now shared.

---

## 1. Core lock: calling API chooses profile; profile selects capabilities

```text
CALLING BUSINESS API
        ↓  chooses profile/purpose explicitly
PROFILE
        ↓  declares only the capabilities it needs
SHARED CAPABILITIES
        ↓
PROFILE-SPECIFIC OUTPUT
        ↓
CALLING BUSINESS MODULE
```

The calling API (router, onboarding capture, email intake, future Fuel/Toll/POD module) **names the profile**. `document_platform` must **never** inspect bytes and guess whether a document is Driver Licence, Rate Confirmation, Fuel, Toll, POD, or anything else.

A profile may use a **different combination** of capabilities than another profile. There is no giant engine that always runs image OpenCV + OCR + OpenAI + barcode.

Shared capabilities do **not** own business posting or reconciliation (create Load, pay fuel, close trip, write driver HR records).

OpenAI **transport** will be shared. OpenAI **schema, field rules, prompt, exclusions, and expected output** stay profile-owned.

**Do not** build separate full stacks (`fuel_parser`, `toll_parser`, another Load parser) that each reinvent acquisition → model → validation. **Do not** force Driver Licence through OpenAI.

---

## 2. Current working compositions (frozen)

### 2.1 Driver Licence — shipped

Chosen by: applicant `dl-upload` and phone `dl-capture` APIs with explicit `doc_type` `CDL_FRONT` | `CDL_BACK` (not inferred from pixels).

```text
native camera / choose photo
        ↓
browser image acquisition (normalize ≤ 2400)
        ↓
persist original
        ↓
DL-specific OpenCV (working copy ≤ 1544, four-corner authority,
                    short-side repair, 1000×631 processed JPEG)
        ↓
PDF417 decode (original-first, processed fallback) + AAMVA mapping
        ↓
phone confirmation (PROCESSED vs user-confirmed) when using capture token
        ↓
onboarding intake / form hydration
```

- **Uses:** image acquisition/browser normalization, DL-specific OpenCV, PDF417, AAMVA mapping, capture confirmation.
- **Does not use:** OpenAI, OCR.
- These behaviors are **frozen**. Do not “genericize” DL OpenCV into a shared guesser.

Current modules (unchanged in Slice 0): `normalizeDlUpload`, `applicant_dl_preprocess`, `applicant_dl_opencv`, `applicant_dl_pdf417`, `dl_pdf417`, capture/confirm in `driver_onboarding`.

### 2.2 Rate Confirmation — shipped

Chosen by: `POST /api/v1/loads/parse-document` and email intake calling the product parser (explicit Rate Confirmation path in code, not a classifier).

```text
PDF bytes
        ↓
shared PDF text extract (page strings; via compatibility shim today)
        ↓
RateCon page usability / OCR-required gate (not a shared capability)
        ↓
if requires_ocr: controlled response (no OpenAI; OCR not executed)
        ↓
tenant identity exclusion
        ↓
Rate Confirmation field rules + schema + v2 handoff
  (page-separated {page_number, text} — not joined full_text)
        ↓
generic OpenAI transport
        ↓
mechanical validation
        ↓
LoadDocumentParseResponse
        ↓
calling module hydrates Load Workspace (or intake review)
```

- **Uses:** shared PDF **text** extract, RateCon-owned usability/OCR-required **gate**, tenant identity exclusion, RC field rules/schema/page-separated handoff, shared OpenAI transport, mechanical validation.
- **Does not:** create/update a commercial `Load` row inside document_platform; OCR is not executed; Load Lab is not this path.
- OpenAI semantic input is **page-separated usable pages** in the handoff JSON. Joined `full_text` / `raw_text` is hydration only.
- Output/schema/rules/exclusion/OpenAI/mechanical-validation behavior is **frozen**.

Current modules: `load_document_parse_rate_con`, `load_parser_pdf_acquisition` (RateCon-owned; **not** shared), `pdf_text_extract` (compatibility shim → `document_platform.capabilities.pdf.text_extract`), `load_parser_openai_handoff_v2`, `load_parser_rate_con_field_rules`, `openai_chat_json_schema` (compatibility shim), `load_parser_mechanical_validation`.

The Rate Confirmation OpenAI schema may include an optional `document_type` **field on that profile’s model output**. That is **not** platform-level routing. The platform still must not switch profiles by inspecting bytes.

---

## 3. Shared capabilities vs profiles

### Capabilities (reusable primitives)

Own: file/page/image/barcode/model-transport primitives, safe timeouts, generic JSON-schema HTTP transport, low-level PDF page-text extraction.

Must not own: which business document this is; Load/Fuel/Toll/POD/driver posting; profile field meaning; RateCon usability thresholds / mixed-document OCR-block policy (those stay in `load_parser_pdf_acquisition` until another profile proves they should be shared).

**OCR:** no production mechanical OCR engine exists today (not Tesseract, Textract, Document AI, EasyOCR, OCRmyPDF, or similar on the RateCon path). Rate Confirmation only **classifies** `ocr_required` and blocks OpenAI. Do not invent an OCR implementation in bootstrap slices.

**PDF text:** one shared extractor, owned by `app/document_platform/capabilities/pdf/text_extract.py`. `app/services/pdf_text_extract.py` is a compatibility shim; production callers still import that old path.

**OpenAI:** one shared transport, now owned by `app/document_platform/capabilities/openai/chat_json_schema.py`. `app/services/openai_chat_json_schema.py` is a compatibility shim; production callers still import that old path. The HTTP 400 `json_object` fallback currently contains Load-specific prompt text; that leak is frozen until a dedicated later slice. Happy-path schema/prompt remain Rate Confirmation–owned.

### Profiles (explicit purpose)

Each profile owns:

- profile identifier
- which capabilities it requires
- field rules, output schema, prompt/context/exclusions
- mapping to the calling module’s DTO

The calling **business** module owns apply/save/post/reconcile.

---

## 4. Future conceptual profiles (not implemented)

| Profile | Status |
|---|---|
| Fuel | Conceptual only. Exact capability composition defined when implemented. |
| Toll | Conceptual only. Exact capability composition defined when implemented. |
| POD | Conceptual only. Exact capability composition defined when implemented. |

Do not create `fuel` / `toll` / `pod` implementation packages until a real slice implements them. The shared PDF text extractor is **available** to those profiles; it is **not** mandatory. Each profile chooses capabilities from actual requirements. Structured trusted API JSON (if any) can bypass document parsing and go through module-owned normalization.

---

## 5. Package layout (through PDF text ownership)

```text
app/document_platform/
  __init__.py
  capabilities/
    __init__.py
    openai/                    # JSON-schema chat transport
      __init__.py
      chat_json_schema.py
    pdf/                       # embedded-text extract only (not acquisition classifier)
      __init__.py
      text_extract.py
  profiles/
    __init__.py                # explicit profiles live here in later slices
```

Later slices may add capability/profile modules **by moving existing files behind re-exports**. OpenAI transport and PDF **text extract** ownership have moved. `load_parser_pdf_acquisition.py`, Rate Confirmation profile logic, and DL code have **not**. Production callers are not rewired.

Target (later slices; OpenAI transport and PDF text extract already moved):

```text
app/document_platform/
  capabilities/          # openai, pdf_text, barcode, dl image geometry, …
  profiles/
    driver_licence/
    rate_confirmation/
    fuel/                # future
    toll/                # future
    pod/                 # future
```

Some modules still carry `load_parser_*` names because Rate Confirmation was the first PDF consumer. That naming is historical, not a license to fork parsers.

---

## 6. Durable safety principles

1. **Calling API chooses profile.** No platform document-type guessing from bytes.
2. **Profile selects capabilities.** Unused capabilities are not run.
3. **File sanity before expensive work.**
4. **Fingerprint/dedupe where the caller persists documents/runs.** Never silently merge unrelated business records.
5. **Readability before semantics** for PDF profiles. Digital PDF does not automatically mean usable text.
6. **OCR, when implemented, is acquisition** — not a separate business parser. OCR-required pages must not be sent as garbage into the model.
7. **Unknown is better than wrong.**
8. **No silent overwrite of trusted or user-confirmed values.** Apply is a calling-module decision.
9. **One semantic owner per OpenAI profile.** Mechanical code validates; it does not compete with the model.
10. **DL OpenCV remains sole four-corner authority** for licence images. Browser normalize does not replace it.

Forbidden on the Rate Confirmation production path:

- `PRODUCT_PARSE_DIAGNOSTICS`
- `broker_party` / `carrier_party` / `role_hint`
- ranked semantic candidate packets as model input
- diagnostics-driven post-model broker/contact/reference/rate repair
- a second semantic stop reconstruction engine

---

## 7. Load Lab boundary

Load Lab is a proving/debug/regression surface. It may retain persisted runs, experiment modes, or evaluation metadata. It is **not** `document_platform` and **not** a second production Load Page parser. It remains separate.

---

## 8. Documentation precedence

1. Current production code (DL and Rate Confirmation paths as shipped).
2. This architecture lock.
3. The active profile contract (Rate Confirmation design doc; DL pipeline doc).
4. `CURRENT_PDF_LOAD_PATHS_AND_GAPS.md` for Load/PDF route reality.
5. Load Lab evidence only for proving/debug history.

Earlier pipeline/rollout reports under [`archive/`](./archive/README.md) must not override this calling-API → profile → capabilities architecture.
