# DL Gold manifest

**Gold point:** `5c445494` (`5c445494908dbfc9a11538dc6af462aeaf62a6a8`)  
**Reason this SHA:** original-pixel warp + processed-first PDF417 (`ac650fff`), plus AAMVA segmentation: `DAY` as a delimiter (sex) and generic `Z[A-Z0-9]{2}` as jurisdiction-extension boundaries. OpenCV / ZXing decode behaviour is unchanged.

| Item | Value |
|---|---|
| Branch | `gold/dl` |
| Immutable tag | `dl-gold-2026-09-12-aamva` |
| Previous DL gold tag (recovery) | `dl-gold-2026-09-12` → `ac650fff` — **do not move or overwrite** |
| Older DL gold tag | `dl-gold-2026-09-07` → `e1008ed5` (superseded) |
| Pipeline commit | `5c445494908dbfc9a11538dc6af462aeaf62a6a8` |
| DAY delimiter | `814e9b39` `fix(dl): recognize DAY delimiter for sex field parsing` |
| Zxx delimiter | `5c445494` `fix(dl): treat jurisdiction Zxx elements as parser delimiters` |
| Warp/boot baseline | `ac650fff` (`5e500195` + `send_dl_capture_link_email`) |
| Production API image | `sha256:a84235030683100bca65600d3797823d3ad8aa20b63dcedcd4a430306e8c5e27` |
| Baked env | `TRUCKERP_APP_GIT_SHA=5c445494` |
| Verified | 2026-09-12 — API healthy; nginx and postgres not rebuilt |

## Pipeline that is gold

BACK upload → OpenCV (detect on 1544 working copy) → warp **from original pixels** to 1000×631 → preview → Use This Photo → PDF417 on **processed** first → original stored BACK only if processed is not `SUCCESS`.

## Dependent files (this module only)

Do not treat Load Parser, Fuel, or Trip/Dispatch files as DL gold.

### Runtime (must match this gold to rebuild API)

- `app/services/applicant_dl_opencv.py`
- `app/services/applicant_dl_preprocess.py`
- `app/services/applicant_dl_pdf417.py`
- `app/services/dl_pdf417.py` (AAMVA field segmentation only: `DAY` + generic `Zxx` delimiters; ZXing/OpenCV decode unchanged)
- `app/routers/driver_onboarding.py` (confirm passes `original_storage_key`; upload still runs OpenCV)
- `app/utils/email.py` (`send_dl_capture_link_email` only — required to boot)

### Tests that lock this gold

- `tests/test_applicant_dl_opencv.py`
- `tests/test_applicant_dl_short_side_repair.py`
- `tests/test_driver_onboarding_dl_extract.py`
- `tests/test_dl_pdf417.py`
- `tests/test_dl_capture.py`
- `tests/test_dl_capture_confirm.py`

### Frontend / capture (same product flow; nginx was **not** rebuilt with this gold)

- `apps/web/src/components/DLUploadStep.tsx`
- `apps/web/src/lib/applicantDlConfirm.ts`
- `apps/web/src/lib/dlCaptureHandoff.ts`
- `apps/web/src/lib/normalizeDlUpload.ts`
- `apps/web/src/pages/DlCapturePage.tsx`

### Frozen scale contract

- `docs/driver_onboarding/DL_OPENCV_WORKING_SCALE.md` — 2400 store / 1544 detect / 1000×631 preview. Warp pixel **source** is now the original still, not the 1544 copy.

## Canadian AAMVA jurisdiction reference

This section is the **parser/design reference for Canada**. It is intentionally broader than the current Ontario test fixtures.

Important distinction:

- The generic parser should support the AAMVA structure used by Canadian provinces and territories.
- Ontario is currently the only Canadian jurisdiction proven with real frozen TruckERP fixtures in this manifest.
- Do **not** claim a province/territory is production-verified until we have a real card fixture from that jurisdiction and add it to the frozen test set.
- Province-specific class/restriction/endorsement meanings and jurisdiction-defined `Z` data are **not** automatically known just because the generic AAMVA barcode parses.

### Issuer identification (IIN)

AAMVA assigns a six-digit Issuer Identification Number (IIN) to identify the issuing jurisdiction. The IIN is encoded in the barcode header and is the authoritative way to distinguish jurisdictions when jurisdiction-specific subfile prefixes collide.

| Jurisdiction | AAMVA IIN | AAMVA abbreviation / note | Expected jurisdiction subfile prefix |
|---|---:|---|---|
| Alberta | `604432` | `AB` | `ZA` |
| British Columbia | `636028` | `BC` | `ZB` |
| Manitoba | `636048` | `MB` | `ZM` |
| New Brunswick | `636017` | `NB` | `ZN` |
| Newfoundland and Labrador | `636016` | AAMVA table currently labels `Newfoundland` / `NF`; Canadian postal abbreviation is `NL` | `ZN` |
| Nova Scotia | `636013` | `NS` | `ZN` |
| Ontario | `636012` | `ON` | `ZO` |
| Prince Edward Island | `604426` | `PE` | `ZP` |
| Quebec | `604428` | `QC` | `ZQ` |
| Saskatchewan | `636044` | `SK` | `ZS` |
| Northwest Territories | `604434` | `NT` | `ZN` |
| Nunavut | `604433` | `NU` | `ZN` |
| Yukon | `604429` | `YT` | `ZY` |

`ZN` is intentionally **not unique**. New Brunswick, Newfoundland, Nova Scotia, Northwest Territories, and Nunavut all begin with `N`, so a `ZN` subfile prefix alone must never be used to infer the issuer. Use the six-digit IIN (and normal address/jurisdiction fields as supporting data).

AAMVA reference: https://www.aamva.org/identity/issuer-identification-numbers-%28iin%29

### Standard AAMVA fields: parse generically across Canada

The core barcode element IDs are standardized; TruckERP should parse these generically rather than building 13 separate province/territory parsers.

| Element | Meaning | TruckERP handling |
|---|---|---|
| `DAQ` | licence/customer ID number | hydrate licence number |
| `DCS` | family/surname | hydrate last name |
| `DAC` | first name | hydrate first name |
| `DAD` | middle name(s) | hydrate when present |
| `DBA` | expiration date | hydrate after deterministic Canadian date parsing |
| `DBD` | issue date | hydrate after deterministic Canadian date parsing |
| `DBB` | date of birth | hydrate after deterministic Canadian date parsing |
| `DBC` | sex | strict mapping: `1→M`, `2→F`, `9→X/unspecified` per product model |
| `DAY` | eye colour | recognize as a delimiter; no onboarding hydration required today |
| `DAU` | height | hydrate height |
| `DAG` | street address | hydrate street |
| `DAI` | city | hydrate city |
| `DAJ` | jurisdiction code | hydrate province/state |
| `DAK` | postal/ZIP code | hydrate postal/ZIP |
| `DCG` | country | normalize Canada/US as supported |
| `DCA` | jurisdiction-specific vehicle class | capture raw value; interpretation may require province profile |
| `DCB` | jurisdiction-specific restriction codes | capture raw value; interpretation may require province profile |
| `DCD` | jurisdiction-specific endorsement codes | capture raw value; interpretation may require province profile |

AAMVA defines `DCA`, `DCB`, and `DCD` as jurisdiction-specific values even though the element IDs themselves are standard. The generic parser may safely capture the raw strings; translating them into business meaning belongs in a jurisdiction profile if/when TruckERP needs that behavior.

AAMVA DL/ID Card Design Standard (2025): https://www.aamva.org/getmedia/81af105d-8b1b-45e1-aa46-f1800a259ed1/AAMVADLIDCardDesignStandard2025.pdf

### Canadian dates

For AAMVA Canadian DL/ID date elements, the Canadian order is **CCYYMMDD / YYYYMMDD**. U.S. AAMVA date order is **MMDDCCYY / MMDDYYYY**.

Parser rule we want:

1. Read the barcode header first (`ANSI` + IIN + AAMVA version/subfile directory).
2. If the issuer is Canadian (Canadian IIN and/or `DCG` = Canada), parse AAMVA 8-digit dates as `YYYYMMDD` only.
3. For U.S. AAMVA credentials, use the U.S. date order required by the applicable AAMVA version/profile.
4. Do **not** try `DDMMYYYY` as an AAMVA fallback.
5. If the jurisdiction-appropriate format is invalid, return `None` / require manual entry rather than guessing another format.

This deterministic rule is a **planned parser correction**; the gold `ac650fff` parser still has the older try-multiple-formats behavior described in the parked bugs below.

### Jurisdiction-specific `Z` subfiles and `Zxx` element boundaries

AAMVA permits jurisdiction-defined subfiles. The two-character subfile designator starts with `Z`; the second character is normally the first letter of the jurisdiction name (for example `ZQ` for Quebec). When multiple jurisdictions share that first letter, the IIN must be used to identify the issuer.

For TruckERP parsing, jurisdiction-defined three-character element IDs are treated generically as:

```text
Z[A-Z0-9]{2}
```

Parser contract:

- `Zxx` is a **field boundary/delimiter** for the generic parser.
- A `Zxx` element must stop the value of the preceding standard field so it cannot be swallowed into `DAK`, `DCK`, or another standard element.
- Do **not** hydrate or interpret unknown `Zxx` elements into onboarding merely because they were detected.
- Preserve jurisdiction-specific interpretation for a future province/territory profile only when there is evidence and a product need.
- Do not infer the issuer from `ZO`, `ZQ`, `ZN`, etc.; use the IIN.

Ontario is the current regression fixture because its real cards contain `ZOZ`/`ZOB`-style extensions. The delimiter rule itself is **not Ontario-specific**.

AAMVA 2025 standard, Annex D, describes the `DL`/`ID` subfiles and jurisdiction-defined `Z` subfiles: https://www.aamva.org/getmedia/81af105d-8b1b-45e1-aa46-f1800a259ed1/AAMVADLIDCardDesignStandard2025.pdf

### Parser architecture: one core parser, optional jurisdiction profiles

Preferred architecture:

```text
PDF417 raw text
  → AAMVA header parser
      → IIN
      → AAMVA version
      → subfile directory
  → generic standard-field segmentation
      → full recognized standard delimiter list
      → generic Zxx delimiters
  → standard field map
  → optional jurisdiction profile
      → only if TruckERP needs to interpret province-specific values
  → onboarding hydration
      → only trusted standard/explicitly-supported fields
```

Do **not** create separate full PDF417 parsers for Ontario, Quebec, Alberta, BC, etc. Province/territory profiles should be thin interpretation layers for jurisdiction-specific values, not duplicate barcode decoders.

### Canadian validation policy

For every new Canadian jurisdiction we encounter in production:

1. Preserve a privacy-safe/frozen fixture or fixture hash according to project policy.
2. Record filename/fixture ID, dimensions, SHA-256, IIN, AAMVA version, and expected parser result.
3. Verify standard fields: `DAQ`, names, dates, `DBC`, `DAU`, address, `DAJ`, `DAK`, `DCG`.
4. Confirm `Zxx` extensions do not contaminate the preceding standard field.
5. Record raw `DCA`/`DCB`/`DCD` values before adding any province-specific semantic interpretation.
6. Add the jurisdiction to the production-verified matrix only after the real fixture passes.

AAMVA compliance is voluntary and real issued cards can vary by jurisdiction/card generation, so standards-based support is not a substitute for real fixture regression testing.

## Production verification (2026-09-12, running `truckerp-api` `5c445494`)

Processed-first PDF417 on original-pixel 1000×631 warps. Original fallback was **not used**.

| Card | OpenCV | PDF417 | source / fallback | `DAK` | `DCK` | `DBC` / `DAY` | `sex` |
|---|---|---|---|---|---|---|---|
| Live 1800×2400 `IMG_0084.jpg` | PASS, 1000×631, `original_pixels` | SUCCESS (438 chars) | `processed` / `false` | `N2R0N4` | `3088730` | `1` / `UNK` | `M` |
| Live 1350×2400 `IMG_6446` | PASS, 1000×631, `original_pixels` | SUCCESS (415 chars) | `processed` / `false` | `N2R0N4` | `7231303` | `2` / `UNK` | `F` |

Name, licence number, province, dates, and class matched the previous gold parse. No `Zxx` keys were written into intake. `DCK` is segmented in the field map and is **not** hydrated into onboarding.

`Z[A-Z0-9]{2}` is a **generic jurisdiction-extension boundary**, not an Ontario-only rule. Ontario (`ZOZ` / `ZOB` / …) is the current tested Canadian fixture. Province-specific `Zxx` values are not interpreted.

## Unresolved DL bugs (parked — do not mix into this gold)

1. **Ambiguous `_parse_date`** — gold still tries 8-digit (and 6-digit) strings through multiple formats. Target behavior is deterministic by AAMVA issuer/country/version: Canada `YYYYMMDD`; U.S. AAMVA uses the applicable U.S. order; never guess `DDMMYYYY` for AAMVA. Parked until its own parser patch.
2. **768×1024 private fixture** `IMG_0084_ontario_back.jpg` — OpenCV can confirm; PDF417 still fails. This is **not** the live 1800×2400 product card.
3. **IMG_8789** — still `FOUR_CORNERS_NOT_CONFIRMED`.
4. **IMG_6446 uncropped original** — PDF417 still fails; the card needs a crop. Gold path is the processed warp.
5. **Do not detect at native 2400** for IMG_6446 — four-corner confirm fails. 1544 remains the detection working-copy ceiling.
6. **Old 1544-pixel 0084 warp** (`0b3e22b2…` 1000×631) still fails PDF417. Gold processed bytes come from original-pixel warp. Fallback still rescues that legacy file if it is re-confirmed.
7. **Intermittent same-DL decode / hydration (observed 2026-09-12)** — the same Ontario DL that failed earlier in the morning later passed with fields populated correctly. A successful run was observed at approximately **12:25 PM ET (America/New_York)**; the earlier failure occurred the same morning, but the exact failure timestamp must be recovered from API/nginx/application logs rather than guessed. Do **not** change parser rules based on this observation alone. Compare failed vs successful runs at the boundaries below:
   - upload/session/application identifier
   - original storage key and processed storage key
   - source and processed dimensions + SHA/hash if logged
   - OpenCV result and `final_warp_source`
   - PDF417 status and barcode source (`processed` vs `original`)
   - raw barcode length / parsed AAMVA field count
   - `apply_pdf417_to_intake` result / intake JSON update
   - frontend reload/hydration timing and final form state
   The purpose of preserving the timestamp is to inspect logs around the **12:25 PM ET successful run** and the earlier-morning failure to locate the first stage where behavior diverges. Treat this as a possible timing/state/path inconsistency until logs prove otherwise.

Shipped in this gold (no longer parked): `DAY` delimiter / sex mapping; generic `Z[A-Z0-9]{2}` field boundaries (delimiter-only; identity-based position/line fallback).

## Planned hardening — orientation, low-resolution images, and front fallback

**Status: documentation only. Do not treat this section as current gold behaviour. Do not implement it as part of an unrelated DL fix.**

### Problem separation

TruckERP has three separate orientation concerns and they must not be mixed:

1. **EXIF/display orientation** — metadata may tell software how the pixels should be displayed. It can be correct, missing, stripped (for example by messaging apps), stale after editing, or inconsistent with the actual saved pixels. Treat EXIF as an input hint, not final truth.
2. **Card geometry orientation** — the current OpenCV pipeline already tries image rotations while finding the card, confirms four corners, deskews/perspective-warps, and produces the rectified card. This answers “where is the card?” and “how do we straighten it?”
3. **Human-readable document orientation** — a perfectly rectified licence can still be upside down. OpenCV geometry alone cannot reliably distinguish a 0-degree card from the same rectangle rotated 180 degrees because both have valid geometry.

Do not replace the proven OpenCV crop/warp pipeline just to solve human-readable orientation.

### Planned architecture

Keep the current OpenCV stages, then add one semantic document-orientation stage after the clean card crop:

```text
uploaded image
  → EXIF-aware load if metadata exists
  → current OpenCV geometry / 0-90-180-270 search
  → four-corner confirmation
  → original-pixel perspective warp
  → clean rectified DL crop
  → document-orientation classifier
      → 0 / 90 / 180 / 270 + confidence
  → if confidence is accepted: physically rotate/bake the winning orientation into pixels
  → if confidence is not accepted: do not guess; preserve image for user review/manual correction
  → preview / extraction
```

The orientation classifier is a semantic stage. It is not another contour, Hough-line, deskew, or aspect-ratio heuristic.

### Candidate bake-off before implementation

Benchmark locally before choosing a dependency:

- **PaddleOCR/PaddleX `PP-LCNet_x1_0_doc_ori`** — preferred candidate from research; dedicated 4-class document/ID orientation classifier (`0/90/180/270`).
- **Tesseract OSD** — free/open-source baseline (Apache 2.0); test only as a comparison. It may be weaker on sparse ID-card text, so do not select it without fixture evidence.
- Do not invent a custom OpenCV “upside-down” heuristic unless the model bake-off demonstrates a concrete reason.

Acceptance must be based on TruckERP fixtures, not published benchmark numbers alone.

### Orientation fixture matrix

Before production implementation, test at minimum:

- upright front
- front rotated 180 degrees
- front rotated 90 degrees
- front rotated 270 degrees
- EXIF present and correct
- EXIF absent
- image manually rotated/cropped and re-saved
- messaging-app/WhatsApp-style metadata-stripped image
- low-resolution front
- normal/high-resolution front
- representative back images

Record for each candidate: predicted angle, confidence, correctness, inference time, and whether the final saved pixels are visually upright.

### Low-resolution policy

Do **not** add one global minimum-resolution rejection for all DL images.

- **Front:** if OpenCV can find/crop the card, allow the front to continue even when resolution is low. Attempt front OCR later. If extraction confidence is weak, require user verification/manual entry rather than rejecting solely because the dimensions are small.
- **Back:** OpenCV may still crop a low-resolution image, but PDF417 requires real barcode detail. If processed decode and original fallback both fail, image dimensions/compression may be used as a specific diagnostic reason. Do not claim that upscaling recreates lost barcode detail.
- Upscaling may help an OCR/decoder algorithm operate, but it does not create missing source information.

The observed low-resolution front image around `664×412` is a useful future regression fixture because OpenCV cropping succeeded and the image remained human-readable. It should not become a blanket rejection fixture.

### Extraction/fallback order

Future extraction plan:

```text
BACK processed crop → PDF417
  OR, if not SUCCESS:
BACK original stored image → PDF417 fallback
  OR, if still not SUCCESS and FRONT exists:
FRONT corrected crop → OCR / AI fallback
  OR:
manual entry / verification
```

Source authority:

```text
successful structured PDF417
  > front OCR/AI fallback
  > manual entry
```

Front OCR/AI must not overwrite a successful trusted PDF417 field merely because it produces a different value. Field-level source/confidence rules must be explicit when this stage is implemented.

### Simple IF / OR decision contract

- **IF** EXIF exists, use it only to normalize the starting image; **OR** if it does not exist, continue from the pixels as received.
- **IF** OpenCV finds and rectifies the card, continue; **OR** if four corners cannot be confirmed, use the existing capture/retry path.
- **IF** the orientation model is confident, rotate the actual pixels to the predicted upright angle; **OR** if confidence is weak, do not guess and let the user review/correct it.
- **IF** the image is FRONT, allow low resolution when OpenCV succeeds and attempt OCR; **OR** use manual verification when OCR is weak.
- **IF** the image is BACK and processed PDF417 succeeds, use it; **OR** try the original stored BACK.
- **IF** both BACK PDF417 attempts fail and a FRONT image exists, later allow FRONT OCR/AI as recovery; **OR** require manual entry.
- **IF** PDF417 already supplied a trusted field, keep it; **OR** use OCR/AI/manual data only for missing/untrusted fields.

### Implementation guardrails

- Do not change current OpenCV detector scale, corner confirmation, or original-pixel warp while implementing orientation unless separate evidence requires it.
- Do not depend on EXIF to decide final human-readable orientation.
- Do not silently rotate on low-confidence model output.
- Bake the selected orientation into actual pixels before saving/preview/extraction so downstream code does not depend on metadata.
- Add tests first; implement in a small isolated DL commit; live-verify fixtures; only then consider moving `gold/dl`.
- Keep this future work independent of Load Parser, Fuel, Trip/Dispatch, and unrelated dirty-tree changes.

## Hard warning

**Never build production from a dirty tree.** `Dockerfile` `COPY . .` will bake uncommitted Load Parser / frontend WIP into `truckerp-api`. Stash or worktree to a clean `5c445494` / `dl-gold-2026-09-12-aamva` before `scripts/reload_api.sh`. Recovery image of the prior warp gold: `dl-gold-2026-09-12` (`ac650fff`).
