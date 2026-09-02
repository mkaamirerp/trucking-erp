# TruckERP — Shared Document Platform Architecture

**Status:** **ARCHITECTURE LOCK — calling API chooses profile; profile selects capabilities; no document-type guessing.**  
**Scope:** Shared document **capabilities** + explicit **profiles**. Not a universal pipeline that always runs every capability.  
**Date:** 2026-08-27; current-state refresh 2026-09-01 (through OpenAI Slice 1C+1D).

**Related current docs:**

- [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) — Rate Confirmation profile contract (frozen).
- [`TRUCKERP_DRIVER_LICENCE_PIPELINE.md`](./TRUCKERP_DRIVER_LICENCE_PIPELINE.md) — Driver Licence pipeline (frozen).
- [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — factual Load/PDF route map.
- [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) — Load Lab vs production Load Page boundary.

**Current runtime checkpoint:** `2903f8f1713c3f8a8ec58785198dd64438531ca5`. OpenAI JSON-schema transport ownership has moved into Document Platform; production callers are **not** rewired. See **Current state / resume anchor** below.

---

## Current state / resume anchor (through OpenAI Slice 1C+1D)

### Architecture rule

- The calling business API selects an **explicit profile**.
- Document Platform does **not** guess business purpose from document content.
- The profile selects capabilities, schema, rules, and context.
- Business posting and reconciliation remain **outside** Document Platform.

### Current implemented capability ownership

- OpenAI JSON-schema transport implementation now lives at:
  `app/document_platform/capabilities/openai/chat_json_schema.py`
- Old path `app/services/openai_chat_json_schema.py` is a **compatibility shim**.
- Production RateCon and Load Lab callers still import the old compatibility path.
- Caller rewiring has **not** started.
- The Load-specific HTTP-400 fallback remains unchanged (behavior preservation).

### Completed migration checkpoints

| Slice | SHA | What landed |
|---|---|---|
| 0 | `29bd4aea02a972d2bc4f60c8e79c0fd9074e37e1` | package/profile architecture boundary |
| 1A | `3f37829f83a58b02a30d9b94e08f0b87d58aa257` | OpenAI capability compatibility namespace |
| 1B | `cc5008d642ee2d4b5586f672d7413863e638696d` | callable identity compatibility test |
| 1C+1D | `2903f8f1713c3f8a8ec58785198dd64438531ca5` | physical OpenAI transport ownership move + shim + mock/test coverage repair |

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
- No OCR
- Driver Licence module is **completed/frozen** unless a new defect arises

### Frozen Rate Confirmation profile composition

- PDF text acquisition
- Usability / OCR-required gate
- No mechanical OCR currently
- Tenant identity exclusion
- RateCon field rules / schema / handoff
- Shared OpenAI transport
- Mechanical validation
- Workspace hydration response
- No Load creation / business posting inside Document Platform

### Current migration boundary

- **Do not** generalize DL OpenCV into a universal geometry capability.
- PDF417 decode may later become a reusable capability; AAMVA / driver intake remains DL profile logic.
- Do not create speculative empty Fuel / Toll / POD packages.
- Load Lab remains separate evaluation tooling.

### NEXT STEP

Do not rewire OpenAI callers or begin PDF acquisition automatically.  
First review the next micro-slice.  
Candidate next architectural migration is **shared PDF acquisition ownership**, but it requires **REPORT-ONLY** inventory/planning before any edits.

**Current runtime checkpoint:** `2903f8f1713c3f8a8ec58785198dd64438531ca5`

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
PDF text acquisition + page usability / OCR-required gate
        ↓
if requires_ocr: controlled response (no OpenAI; OCR not implemented)
        ↓
tenant identity exclusion
        ↓
Rate Confirmation field rules + schema + v2 handoff
        ↓
generic OpenAI transport
        ↓
mechanical validation
        ↓
LoadDocumentParseResponse
        ↓
calling module hydrates Load Workspace (or intake review)
```

- **Uses:** PDF text acquisition, usability/OCR-required **gate**, tenant identity exclusion, RC field rules/schema/handoff, shared OpenAI transport, mechanical validation.
- **Does not:** create/update a commercial `Load` row inside document_platform; OCR is not executed; Load Lab is not this path.
- Output/schema/rules/exclusion/OpenAI/mechanical-validation behavior is **frozen**.

Current modules (unchanged in Slice 0): `load_document_parse_rate_con`, `load_parser_pdf_acquisition`, `pdf_text_extract`, `load_parser_openai_handoff_v2`, `load_parser_rate_con_field_rules`, `openai_chat_json_schema`, `load_parser_mechanical_validation`.

The Rate Confirmation OpenAI schema may include an optional `document_type` **field on that profile’s model output**. That is **not** platform-level routing. The platform still must not switch profiles by inspecting bytes.

---

## 3. Shared capabilities vs profiles

### Capabilities (reusable primitives)

Own: file/page/image/barcode/model-transport primitives, safe timeouts, mechanical usability gates, generic JSON-schema HTTP transport.

Must not own: which business document this is; Load/Fuel/Toll/POD/driver posting; profile field meaning.

**OCR:** no engine exists today. Rate Confirmation only **gates** `ocr_required`. Do not invent an OCR implementation in bootstrap slices.

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

Do not create `fuel` / `toll` / `pod` implementation packages until a real slice implements them. Structured trusted API JSON (if any) can bypass document parsing and go through module-owned normalization.

---

## 5. Package layout (through Slice 1C+1D)

```text
app/document_platform/
  __init__.py
  capabilities/
    __init__.py
    openai/                    # JSON-schema chat transport (Slice 1C+1D)
      __init__.py
      chat_json_schema.py
  profiles/
    __init__.py                # explicit profiles live here in later slices
```

Later slices may add capability/profile modules **by moving existing files behind re-exports**. OpenAI transport ownership has moved; PDF extract, Rate Confirmation, and DL code have **not**. Production callers are not rewired.

Target (later slices; OpenAI transport already moved):

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
