# TruckERP Document Platform — Profile-Driven Architecture Lock

**Status:** Architecture lock for document ingestion/parsing evolution  
**Scope:** Driver Licence, Rate Confirmation, and future Fuel, Toll, POD, Registration/CVOR/other document profiles  
**Rule:** Business caller chooses purpose. The shared document platform executes only the capabilities declared by that profile.

## 1. Core rule

TruckERP must not build one universal document pipeline that always runs every available capability, and it must not inspect document bytes and guess the business purpose.

The **calling business API/module explicitly chooses the document profile**. The selected profile owns the business-specific instructions, schema, validation, and output contract. The document platform supplies reusable capabilities.

```text
CALLING BUSINESS API / MODULE
        |
        | explicitly selects profile
        v
DOCUMENT PROFILE
        |
        | declares only required capabilities
        v
SHARED DOCUMENT CAPABILITIES
        |
        v
PROFILE-SPECIFIC STRUCTURED OUTPUT
        |
        v
CALLING BUSINESS MODULE
```

Examples of explicit caller intent:

- Load API selects `rate_confirmation`.
- Driver onboarding/capture API selects `driver_licence` and its side (`CDL_FRONT` / `CDL_BACK`).
- Future Fuel API selects `fuel`.
- Future Toll API selects `toll`.
- Future POD API selects `pod`.

The document platform must not decide that a file is a DL, Rate Confirmation, Fuel receipt, Toll statement, or POD by inspecting its contents.

## 2. Capability composition model

A profile is a composition of capabilities, not a separate copy of the entire parser stack.

Conceptually, if reusable capabilities were represented as letters only for illustration:

```text
Profile X -> A + C + D
Profile Y -> B + D + E
Profile Z -> A + D + E
```

Those letters are **not architecture names**. The rule they illustrate is the architecture: each profile runs only the capabilities it needs.

Typical shared/specialized capabilities include:

- document/image acquisition
- browser/image normalization
- PDF embedded-text extraction
- page usability / OCR-required detection
- OCR (future; not currently implemented in production)
- OpenAI JSON-schema transport
- barcode/PDF417 decoding
- image processing where reusable
- storage
- mechanical/structural validation primitives where genuinely reusable

A capability may be shared, profile-specific, or split into a shared engine plus profile-specific mapping.

## 3. Current working profiles

TruckERP currently has two proven production document flows that must be preserved while the code is reorganized.

### 3.1 Driver Licence profile

Current composition:

```text
Driver onboarding / DL capture caller
    -> native phone camera or upload
    -> browser normalization (long side <= 2400)
    -> persist source/original
    -> temporary EXIF-normalized OpenCV working copy
    -> working copy long side <= 1544
    -> HSV rough proposal
    -> same four-corner confirmation authority
    -> Canny rough proposal when required
    -> same four-corner confirmation authority
    -> optional strict short-side repair when eligible
    -> confirmed perspective warp 1000 x 631
    -> persist processed image separately
    -> BACK: PDF417 original-first, processed fallback
    -> AAMVA mapping into driver intake
    -> phone confirmation state where applicable
    -> onboarding form hydration
```

Frozen distinctions:

- `2400` is the browser ingestion/storage ceiling.
- `1544` is the OpenCV detector working-scale ceiling.
- `1000 x 631` is the confirmed rectified output.

These values serve different purposes and must not be collapsed.

Driver Licence currently uses:

- image acquisition/normalization
- DL-specific OpenCV geometry
- PDF417 decoding
- AAMVA mapping
- capture confirmation state
- storage

Driver Licence currently does **not** use:

- OpenAI semantic extraction
- production OCR
- PDF text extraction

The DL OpenCV algorithm is profile-specific. Its 1544 working scale, four-corner authority, short-side repair, and 1000 x 631 output must not be generalized into a Fuel/Toll/POD image pipeline merely because those documents may also arrive as images.

PDF417 decoding may become a reusable barcode capability, but AAMVA-to-driver-intake mapping remains Driver Licence profile logic.

### 3.2 Rate Confirmation profile

Current composition:

```text
Load API / email-intake caller
    -> Rate Confirmation profile
    -> PDF embedded-text acquisition
    -> page usability classification
    -> if unusable/scanned: controlled OCR-required outcome
    -> tenant identity exclusion
    -> Rate Confirmation field rules
    -> Rate Confirmation OpenAI handoff payload
    -> generic OpenAI JSON-schema transport
    -> Rate Confirmation response schema
    -> mechanical validation
    -> LoadDocumentParseResponse
    -> Load Workspace hydration
```

The current Load HTTP route does not accept an arbitrary profile name; the business route itself is the explicit decision to use Rate Confirmation parsing.

The same Rate Confirmation product parser is also called from email intake for PDF attachments. That is still explicit business intent and is not platform-level document guessing.

Rate Confirmation currently uses:

- PDF text extraction
- page usability / OCR-required gate
- tenant identity exclusion
- profile-owned semantic field rules
- profile-owned schema and handoff
- shared OpenAI JSON-schema transport
- mechanical validation

Rate Confirmation currently does **not** run a production OCR engine. When OCR is required, it returns a controlled response instead of silently invoking another parser.

## 4. OpenAI architecture

OpenAI must be a shared **capability**, not a Load-specific engine.

The shared capability owns transport concerns such as:

- HTTP request to OpenAI
- model invocation
- JSON-schema response mode
- JSON content extraction
- transport/error handling

The profile owns semantic concerns such as:

- purpose
- system/user instructions
- field rules
- JSON schema
- exclusions/context
- validation expectations
- mapping of model output into the business response contract

Therefore future profiles change the semantic payload without creating duplicate OpenAI clients.

```text
Rate Confirmation profile
    -> RC rules + RC schema + RC context + document text
    -> shared OpenAI capability
    -> RC JSON

Fuel profile
    -> Fuel rules + Fuel schema + Fuel context + document text
    -> same shared OpenAI capability
    -> Fuel JSON

Toll profile
    -> Toll rules + Toll schema + Toll context + document text
    -> same shared OpenAI capability
    -> Toll JSON

POD profile
    -> POD rules + POD schema + POD context + document text
    -> same shared OpenAI capability only if POD requires semantic extraction
    -> POD JSON
```

### Current OpenAI implementation note

The current generic transport lives in `app/services/openai_chat_json_schema.py`. The thin `load_document_parse_openai.py` wrapper is Load-named passthrough code around that generic transport.

A known cleanup issue exists: the HTTP-400 fallback prompt inside the current generic transport contains Load-specific wording. Do **not** change it during a move-only refactor. First preserve behavior with compatibility imports; later make the fallback profile-supplied or otherwise generic in a dedicated behavior-change slice.

Load Lab is a separate proving/evaluation semantic stack and must not be merged into the production document platform during early reorganization slices.

## 5. Future profile intent

The following are conceptual profile targets. Their exact fields and capability composition are not frozen until each business module is implemented.

### Fuel

Likely composition:

```text
Fuel business API
    -> fuel profile
    -> PDF/image acquisition as appropriate
    -> embedded text and/or OCR when implemented
    -> Fuel field rules/schema
    -> shared OpenAI capability when semantic extraction is required
    -> Fuel JSON
    -> Fuel business module
```

Fuel posting, reconciliation, card matching, accounting, settlements, and business decisions remain outside the document platform.

### Toll

Likely composition:

```text
Toll business API
    -> toll profile
    -> PDF/image acquisition as appropriate
    -> embedded text and/or OCR when implemented
    -> Toll field rules/schema
    -> shared OpenAI capability when semantic extraction is required
    -> Toll JSON
    -> Toll business module
```

Toll reconciliation, trip matching, settlement/accounting decisions, and posting remain outside the document platform.

### POD

Likely composition:

```text
POD business API
    -> pod profile
    -> PDF/image acquisition
    -> embedded text and/or OCR when implemented
    -> OpenAI only if the POD profile requires semantic extraction
    -> POD JSON / document result
    -> POD / Trip / Load business workflow
```

A POD scanner must not reuse the Driver Licence OpenCV/PDF417 pipeline merely because both may originate from a phone camera.

## 6. Business-module boundary

The document platform extracts and structures document information. It does not become the owner of the downstream business transaction.

Examples of logic that stays outside `document_platform`:

- creating/updating a Load
- dispatch workflow
- marking a POD accepted/completed
- paying or reconciling Fuel
- posting Toll expenses
- owner-operator settlement decisions
- accounting posting
- compliance workflow decisions

The business module requests a profile, receives a structured result, and then performs its own domain logic.

## 7. Target code organization

The target is a small capability-and-profile package, not a mega-engine.

```text
app/
  document_platform/
    __init__.py

    capabilities/
      __init__.py

      openai/
        chat_json_schema.py

      pdf/
        text_extract.py
        page_usability.py

      barcode/
        pdf417_decode.py

      storage/
        ...

    profiles/
      __init__.py

      driver_licence/
        pipeline.py
        opencv.py
        aamva_intake.py

      rate_confirmation/
        parse.py
        field_rules.py
        handoff.py
        tenant_exclusion.py
        mechanical_validation.py
        schema.py or compatibility reference

      # Created when implemented, not speculative empty packages:
      # fuel/
      # toll/
      # pod/
```

Notes:

- Browser normalization remains TypeScript under the web application; the backend architecture may document it as part of the DL profile without pretending the Python package owns browser code.
- `app/core/storage.py` can remain the generic physical storage backend. The document platform should not duplicate the storage engine solely to achieve folder symmetry.
- Profile folders are created when implementation begins; do not create empty Fuel/Toll/POD code merely to make the tree look complete.

## 8. Migration strategy

Reorganization must be behavior-preserving and incremental.

### Slice 0 — package boundary only

Create the `app/document_platform/` package and document this architecture. Do not change production imports or runtime behavior.

### Slice 1 — shared OpenAI capability

Move the generic OpenAI JSON-schema transport behind `document_platform/capabilities/openai/` while leaving a compatibility re-export at the old import path. Do not change prompts, schemas, retry behavior, or the current Load-specific 400 fallback in this move-only slice.

### Slice 2 — PDF capability

Move/re-export generic PDF embedded-text extraction and reusable page-usability logic. Preserve Rate Confirmation behavior exactly.

### Slice 3 — Rate Confirmation profile

Gather Rate Confirmation-specific parse, field rules, exclusions, handoff, schema ownership, and mechanical validation under `profiles/rate_confirmation/` using compatibility re-exports so existing public product entrypoints remain stable.

### Slice 4 — Driver Licence profile

Gather the DL-specific preprocess/OpenCV/PDF417/AAMVA pieces under `profiles/driver_licence/` without changing its production algorithm or phone workflow. Do not force DL behind the OpenAI execution path.

### Later slices

- parameterize/remove the Load-specific OpenAI fallback leak
- introduce an actual OCR capability when required
- create Fuel profile
- create Toll profile
- create POD profile
- add Registration/CVOR/other profiles as their business modules require them

Each move should preserve old import paths until all callers are deliberately migrated.

## 9. Compatibility and testing rule

Both current production flows are frozen regression anchors during the architecture move.

After every migration slice, verify the relevant existing tests for:

### Driver Licence

- OpenCV confirmation behavior
- 1544 working scale
- short-side repair
- 1000 x 631 output
- PDF417 original-first behavior
- AAMVA mapping
- phone confirmation state where testable

### Rate Confirmation

- product parser / guarded parser
- PDF acquisition and OCR-required gate
- tenant identity exclusion
- field rules and OpenAI handoff
- generic OpenAI JSON-schema helper
- mechanical validation
- response/hydration contract

No slice is considered a successful architecture cleanup if it changes the observable behavior of either working flow without an explicit separately approved behavior change.

## 10. Anti-patterns explicitly prohibited

Do not introduce:

- automatic platform-level document-type guessing
- a universal pipeline that always runs OCR/OpenAI/barcode/OpenCV
- separate OpenAI clients for Load, Fuel, Toll, POD, etc.
- separate full parser engines for Fuel/Toll/POD
- reuse of DL-specific geometry for unrelated documents
- business posting/reconciliation inside shared parsing capabilities
- hidden fallbacks that silently switch semantic parsers
- empty future implementation packages that imply features exist
- early merging of Load Lab into the production parser

## 11. Architecture summary

The durable model is:

> **Business caller chooses profile. Profile chooses capabilities. Capabilities execute reusable mechanics. Profile owns semantic meaning and structured output. Business module owns the resulting business action.**

This allows TruckERP to add document types by composing existing capabilities and adding only the missing profile-specific rules/schema/validation, instead of building another end-to-end parser stack every time.
