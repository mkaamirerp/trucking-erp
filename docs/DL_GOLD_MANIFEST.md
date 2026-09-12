# DL Gold manifest

**Gold point:** `ac650fff` (`ac650fff4c3a6910bbf604a4da5f8c588181702d`)  
**Reason this SHA, not `5e500195`:** `5e500195` is the original-pixel warp + processed→original PDF417 fallback, but a clean image of that commit cannot import `app.main` (`send_dl_capture_link_email` missing). `ac650fff` is `5e500195` plus that boot helper.

| Item | Value |
|---|---|
| Branch | `gold/dl` |
| Immutable tag | `dl-gold-2026-09-12` |
| Previous DL gold tag | `dl-gold-2026-09-07` → `e1008ed5` (superseded) |
| Pipeline commit | `5e500195204038d183d3cbc8935713ecc7d532f2` |
| Boot/helper commit | `ac650fff4c3a6910bbf604a4da5f8c588181702d` |
| Production API image | `sha256:8ef8011cf9a7a64f70a09105f5f786e0e6f37fea8d05fbd03693626a4de0ea38` |
| Baked env | `TRUCKERP_APP_GIT_SHA=ac650fff` |
| Verified | 2026-09-12 — API healthy; nginx and postgres not rebuilt |

## Pipeline that is gold

BACK upload → OpenCV (detect on 1544 working copy) → warp **from original pixels** to 1000×631 → preview → Use This Photo → PDF417 on **processed** first → original stored BACK only if processed is not `SUCCESS`.

## Dependent files (this module only)

Do not treat Load Parser, Fuel, or Trip/Dispatch files as DL gold.

### Runtime (must match this gold to rebuild API)

- `app/services/applicant_dl_opencv.py`
- `app/services/applicant_dl_preprocess.py`
- `app/services/applicant_dl_pdf417.py`
- `app/services/dl_pdf417.py` (unchanged in this gold; decoder/ZXing/AAMVA frozen)
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

## Production verification (2026-09-12, running `truckerp-api`)

| Card | OpenCV | `final_warp_source` | PDF417 | `barcode_image_source` | `original_fallback_used` |
|---|---|---|---|---|---|
| Live 1800×2400 `IMG_0084.jpg` | PASS, 1000×631 | `original_pixels` | SUCCESS (438 chars, 20 fields) | `processed` | `false` |
| Live 1350×2400 `IMG_6446` | PASS, 1000×631 | `original_pixels` | SUCCESS (415 chars, 18 fields) | `processed` | `false` |

Original fallback is **retained** as a safety net. It was **not used** for either verified card.

## Unresolved DL bugs (parked — do not mix into this gold)

1. **Jurisdiction `Zxx` field boundary** — gold `ac650fff` does not yet contain the generic `Z[A-Z0-9]{2}` delimiter correction. The planned/working-tree correction is province-neutral: both extractors share the D-code + `Zxx` delimiter vocabulary, `Zxx` is delimiter-only, and the arbitrary `len(by_pos) >= 3` shortcut is removed. Do not claim this is in gold until committed, deployed, verified, and `gold/dl` is advanced.
2. **Ambiguous `_parse_date`** — gold still tries 8-digit (and 6-digit) strings through multiple formats. Target behavior is deterministic by AAMVA issuer/country/version: Canada `YYYYMMDD`; U.S. AAMVA uses the applicable U.S. order; never guess `DDMMYYYY` for AAMVA. Parked until its own parser patch.
3. **`DAY` delimiter / Sex-Gender contamination** — Ontario cards can encode `DBC1<LF>DAYUNK...` / `DBC2<LF>DAYUNK...`. If `DAY` is absent from the delimiter list, `DBC` becomes `1 DAYUNK` / `2 DAYUNK` and strict `_parse_sex()` returns `None`. Correct fix: recognize `DAY` as a delimiter and keep `_parse_sex()` strict. Do not mark gold updated until that focused patch is committed/deployed/verified.
4. **768×1024 private fixture** `IMG_0084_ontario_back.jpg` — OpenCV can confirm; PDF417 still fails. This is **not** the live 1800×2400 product card.
5. **IMG_8789** — still `FOUR_CORNERS_NOT_CONFIRMED`.
6. **IMG_6446 uncropped original** — PDF417 still fails; the card needs a crop. Gold path is the processed warp.
7. **Do not detect at native 2400** for IMG_6446 — four-corner confirm fails. 1544 remains the detection working-copy ceiling.
8. **Old 1544-pixel 0084 warp** (`0b3e22b2…` 1000×631) still fails PDF417. Gold processed bytes come from original-pixel warp. Fallback still rescues that legacy file if it is re-confirmed.

## Hard warning

**Never build production from a dirty tree.** `Dockerfile` `COPY . .` will bake uncommitted Load Parser / frontend WIP into `truckerp-api`. Stash or worktree to a clean `ac650fff` (or this tag) before `scripts/reload_api.sh`.
