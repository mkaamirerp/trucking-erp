# DL OpenCV working scale (frozen)

## Contract

Three numbers, three jobs. Do not collapse them.

| Scale | Role |
|---|---|
| **2400** | Browser ingestion/storage ceiling (`DL_UPLOAD_MAX_LONG_SIDE`). Persist the normalized source. |
| **1544** | OpenCV **detection** working-copy ceiling (`WORKING_COPY_MAX_SIDE`). Temporary only. |
| **1000×631** | Final confirmed rectified licence output after four-corner warp. |

Pipeline:

1. Browser source normalization ≤ 2400.
2. Persist that normalized source/original (do not replace it with the 1544 copy).
3. EXIF-correct a temporary OpenCV working copy.
4. If long side > 1544, downscale **that working copy** to 1544.
5. HSV rough proposal → same four-corner confirmer.
6. Canny rough fallback if required → same confirmer.
7. Warp confirmed card to 1000×631.
8. PDF417 from the processed/enhanced **back** image.

`2400` bounds stored source size. `1544` is the proven OpenCV operating scale. They are not interchangeable.

Hermetic CI tests cover the working-scale file contract on generated images. IMG6446 is a **private operator battery**, not a clean-checkout CI gate.

## Evidence

- `61f956e6` introduced 1544 as a **correctness** operating scale (sandbox four-corner range), not a measured RAM guard.
- `f00cf96e` later added browser max-2400 without reevaluating server 1544.
- **2026-08-30** revalidation under production OpenCV **4.11.0** (running `truckerp-api`) on browser-normalized 1350×2400 sources:

| Image | 1544 working copy | Direct 2400 |
|---|---|---|
| IMG6446 | CANNY PASS → 1000×631 → PDF417 success | FAIL (`FOUR_CORNERS_NOT_CONFIRMED`) |
| ed3411 (normalized) | HSV PASS | HSV PASS, no quality gain |

Direct 2400 also cost materially more processing time and RSS (IMG6446 ~1.9s vs ~3.4s wall; ed3411 ~1.4s vs ~2.3s).

This converts 1544 from inherited behavior into an explicitly revalidated contract.

**Battery limitation:** raw 4032 ed3411 is unavailable. Do not block this freeze on reconstructing it. The browser-normalized source is the current production ingestion contract.

## Change rule

Do not change `WORKING_COPY_MAX_SIDE` without rerunning the frozen DL battery (including private IMG6446). Do not change confirmer thresholds, Canny/HSV locators, or warp size in the same slice as a scale experiment.
