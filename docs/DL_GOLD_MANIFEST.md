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

## Production verification (2026-09-12, running `truckerp-api`)

| Card | OpenCV | `final_warp_source` | PDF417 | `barcode_image_source` | `original_fallback_used` |
|---|---|---|---|---|---|
| Live 1800×2400 `IMG_0084.jpg` | PASS, 1000×631 | `original_pixels` | SUCCESS (438 chars, 20 fields) | `processed` | `false` |
| Live 1350×2400 `IMG_6446` | PASS, 1000×631 | `original_pixels` | SUCCESS (415 chars, 18 fields) | `processed` | `false` |

Original fallback is **retained** as a safety net. It was **not used** for either verified card.

## Unresolved DL bugs (parked — do not mix into this gold)

1. **Z-code field boundary** — `_extract_field_map_by_positions` does not treat `Z[A-Z0-9]{2}` as a delimiter; `_extract_field_map_lines` does. Do not change AAMVA parsing in a gold rebuild.
2. **Ambiguous `_parse_date`** — 8-digit (and 6-digit) strings are tried as `%Y%m%d` / `%m%d%Y` / `%d%m%Y` (and 2-digit-year variants) in order. Wrong calendar date is possible. Parked.
3. **768×1024 private fixture** `IMG_0084_ontario_back.jpg` — OpenCV can confirm; PDF417 still fails. This is **not** the live 1800×2400 product card.
4. **IMG_8789** — still `FOUR_CORNERS_NOT_CONFIRMED`.
5. **IMG_6446 uncropped original** — PDF417 still fails; the card needs a crop. Gold path is the processed warp.
6. **Do not detect at native 2400** for IMG_6446 — four-corner confirm fails. 1544 remains the detection working-copy ceiling.
7. **Old 1544-pixel 0084 warp** (`0b3e22b2…` 1000×631) still fails PDF417. Gold processed bytes come from original-pixel warp. Fallback still rescues that legacy file if it is re-confirmed.

## Hard warning

**Never build production from a dirty tree.** `Dockerfile` `COPY . .` will bake uncommitted Load Parser / frontend WIP into `truckerp-api`. Stash or worktree to a clean `ac650fff` (or this tag) before `scripts/reload_api.sh`.
