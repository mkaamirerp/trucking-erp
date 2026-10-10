# DL Orientation Architecture and Test Plan

**Status:** design/test plan only — **not production implementation**.  
**Purpose:** preserve the complete image path and isolate the orientation problem so future DL changes can be made one stage at a time without disturbing the proven OpenCV/PDF417 pipeline.

This document is a companion to `docs/DL_GOLD_MANIFEST.md`.

## Current problem in hand

The immediate problem is **human-readable document orientation after a good crop**.

A Driver Licence can be detected correctly, have all four corners confirmed, be perspective-corrected into a clean landscape rectangle, and still be upside down to a human.

Do not mix this with:

- EXIF/display orientation;
- finding the DL in a larger photograph;
- card rotation used only to make geometry detectable;
- deskew/perspective correction;
- OCR field extraction;
- PDF417 decoding.

Those are separate stages.

The current OpenCV 0/90/180/270 search answers **"at which rotation can I find valid DL geometry?"**. It does **not** reliably answer **"which way is the licence meant to be read?"**.

## End-to-end path — every stage matters

### Stage 0 — user source

The user may:

- take a new camera photo;
- choose a gallery image;
- upload a manually rotated/cropped image;
- upload an image passed through WhatsApp or another app;
- upload an image whose EXIF is correct, missing, stripped, rewritten, or stale.

Therefore EXIF is useful input metadata, but it is not final authority for human-readable orientation.

### Stage 1 — browser normalization happens before backend/OpenCV

Current browser code: `apps/web/src/lib/normalizeDlUpload.ts`.

For image files the browser currently:

1. decodes with `createImageBitmap(..., imageOrientation: "from-image")`;
2. therefore applies browser/EXIF display orientation during decode;
3. reads the decoded width/height;
4. uses a maximum long side of **2400 px**;
5. **IF** long side is greater than 2400, downsizes to 2400 maximum;
6. **OR IF** the image is already smaller, keeps its existing dimensions;
7. never intentionally upscales a small image;
8. draws the decoded pixels to a canvas;
9. encodes a **new JPEG at quality 0.92**;
10. uploads that new JPEG to TruckERP.

Important consequence: the backend's so-called "original" image is normally the **highest-resolution browser-normalized image received by TruckERP**, not necessarily the untouched camera file bytes.

Example — low-resolution WhatsApp FRONT:

```text
664×412 input
→ browser does not upscale
→ remains 664×412
→ canvas/JPEG 0.92 re-encode
→ backend receives 664×412
```

Example — large phone image:

```text
3024×4032 input
→ browser EXIF-aware decode
→ long side limited to 2400
→ approximately 1800×2400
→ JPEG 0.92
→ backend receives that image
```

### Stage 2 — backend source image

Current backend orchestrator: `app/services/applicant_dl_preprocess.py`.

Backend loads the uploaded source EXIF-aware again using Pillow `ImageOps.exif_transpose()` with OpenCV fallback.

This source image must be preserved as the best available pixel source for later warp/decoding.

Do **not** confuse this source with the temporary OpenCV detection copy.

### Stage 3 — temporary OpenCV detection copy

Current maximum detection long side: **1544 px**.

The backend creates a temporary working copy only for card detection.

```text
browser-normalized source, up to 2400
        │
        ├── source pixels: KEEP
        │
        └── detector copy: max long side 1544
```

**IF** source long side is greater than 1544:
- downscale the detector copy to 1544.

**OR IF** source is already 1544 or smaller:
- do not enlarge it just for detection.

1544 is a validated detection scale and must not be changed as part of the orientation fix.

### Stage 4 — OpenCV geometry search

OpenCV currently tries these geometry orientations:

```text
original
cw90
ccw90
rotate180
```

For each candidate it searches for DL geometry, including rough location, edges, four corners, aspect/geometry validation and perspective suitability.

The winning OpenCV orientation means:

> this rotation gave the best/valid card geometry.

It does **not** mean:

> the text on the card is human-upright.

### Stage 5 — map geometry back to better source pixels

This rule is already gold and must stay frozen.

The 1544 detector copy is allowed to provide **geometry**, but it must not become the pixel source for the final high-quality crop.

Current gold path:

```text
higher-resolution source
        │
        └→ temporary 1544 detector copy
                    │
                    └→ OpenCV finds winning rotation + four corners
                                      │
                                      ▼
                       map those corners back to source
                                      │
                                      ▼
                       warp from SOURCE PIXELS
                                      │
                                      ▼
                              1000×631 DL crop
```

This repaired a real PDF417 regression. The old path detected on reduced pixels and then used those reduced pixels to make the final 1000×631 warp. That discarded barcode detail.

**Hard architectural rule:**

> Never allow a lower-resolution intermediary to become the pixel source for a later higher-resolution output. Downscaled copies are for detection only. Geometry may travel from the working copy back to the best source; pixels must come from the best available source.

### Stage 6 — current OpenCV "upright" heuristic is separate from geometry

Current OpenCV code has `ensure_landscape_upright_for_dl()`.

It first ensures landscape geometry, then compares dark-pixel density on left/right regions and may rotate 180 degrees.

That is a heuristic attempt at human-readable orientation. It is **not the same thing as four-corner detection** and must be treated separately in future work.

A real screenshot has already shown the failure mode:

```text
DL detected: correct
four corners: correct
crop: correct
perspective: correct
landscape: correct
human orientation: upside down
```

Therefore the current orientation project should not change the proven detector/crop first. It should evaluate replacing only the final semantic "which side is up?" decision.

## Proposed future responsibility split

### OpenCV responsibility

OpenCV should remain responsible for:

- input image geometry;
- locating the DL;
- 0/90/180/270 geometry search;
- edge/corner detection;
- four-corner confirmation;
- perspective correction;
- producing a clean rectangular/landscape DL crop;
- mapping detector geometry back to higher-resolution source pixels.

OpenCV should not be asked to invent semantic document orientation through fragile image-layout heuristics if a dedicated orientation classifier proves more reliable.

### Orientation classifier responsibility

After OpenCV produces a clean crop, a separate orientation component should answer only:

> Which way is this already-cropped document meant to be read?

Candidate outputs:

```text
0°
90°
180°
270°
+ confidence
```

Candidate tools to benchmark:

- Paddle/PaddleOCR document orientation classifier (`PP-LCNet_x1_0_doc_ori` or current equivalent);
- Tesseract OSD as a free/local baseline;
- current OpenCV heuristic as the existing baseline/control.

Do not choose a winner from documentation claims alone. Test them on our real DL crops.

## Recommended future order

The preferred architecture to test is **OpenCV first, orientation classifier second**.

Reason:

The original user photo can contain background, hand, table, dashboard, shadows, perspective distortion, and only a portion of the frame may be the licence.

OpenCV already has a proven job:

```text
messy photo
→ find DL
→ confirm geometry
→ crop/warp clean DL
```

Then the orientation classifier receives an easier and more controlled input:

```text
clean DL crop
→ decide which side is up
```

So the planned sequence is:

```text
USER IMAGE
  ↓
BROWSER EXIF-AWARE NORMALIZATION
  ↓
BACKEND SOURCE IMAGE
  ↓
1544 TEMP DETECTION COPY
  ↓
OPENCV GEOMETRY
  ↓
MAP CORNERS BACK TO SOURCE
  ↓
WARP FROM SOURCE PIXELS TO CLEAN DL CROP
  ↓
ORIENTATION TEST / CLASSIFIER
  ↓
PHYSICALLY ROTATE FINAL CROP IF CONFIDENT
  ↓
SAVE/SHOW PREVIEW
  ↓
USE THIS PHOTO
  ↓
FRONT OCR or BACK PDF417
```

Do not put Paddle/Tesseract before OpenCV unless a controlled test later proves that doing so is materially better. The default hypothesis is OpenCV first because it removes scene/background noise and creates a normalized document input.

## FRONT low-resolution policy

Do **not** add a blanket low-resolution rejection rule based only on dimensions.

Real example observed:

- FRONT image about **664×412**;
- image had passed through WhatsApp;
- OpenCV crop worked correctly;
- the image was not rejected;
- browser did not need to upscale it.

Therefore:

```text
IF FRONT is low resolution
AND OpenCV can still confirm/crop the DL
THEN keep going.
```

After crop:

```text
→ orientation test
→ FRONT OCR/AI attempt
→ IF useful, hydrate with confidence
→ OR IF weak, require user review/manual entry
```

Low resolution can reduce OCR certainty, but it must not automatically invalidate a geometrically usable FRONT image.

## BACK/PDF417 policy

The gold extraction order remains:

```text
processed BACK PDF417
    IF SUCCESS → use it
    OR
stored higher-resolution BACK PDF417 fallback
    IF SUCCESS → use it
    OR
future FRONT OCR/AI/manual fallback
```

If both barcode attempts fail and the actual source is small/compressed, a future product message may distinguish "barcode lacks enough detail" from a generic decoder failure — but only after evidence/testing.

PDF417 structured data remains higher authority than OCR guesses for fields it successfully provides.

## Browser preservation question — investigate, do not change yet

Because every browser image is currently drawn to canvas and JPEG-encoded at quality 0.92, even a file that does not need resizing is re-encoded before the backend sees it.

That means the very first stage may discard some image information:

```text
camera/gallery JPEG
→ browser decode
→ canvas
→ JPEG 0.92
→ backend
```

This is not currently proven to be a bug.

Future controlled test:

```text
A. current browser-normalized JPEG
versus
B. untouched uploaded bytes / preserved original file
```

Compare OpenCV geometry, orientation result and especially BACK PDF417 decode.

Do not change browser normalization until frozen-card testing proves a benefit.

## Orientation bake-off — required before implementation

The orientation problem has attracted multiple possible fixes (browser/EXIF, OpenCV heuristic, Paddle, Tesseract). We must not stack all of them blindly.

First create a controlled test set using **already-good crops** so crop quality is held constant. The question under test is only human-readable orientation.

Include at minimum:

- upright FRONT;
- same FRONT rotated 180°;
- same FRONT rotated 90°;
- same FRONT rotated 270°;
- normal-resolution FRONT;
- low-resolution FRONT;
- WhatsApp/compressed FRONT;
- manually rotated/cropped FRONT;
- EXIF present case;
- EXIF missing/stripped case;
- EXIF/pixel disagreement case if reproducible;
- BACK crops as secondary orientation coverage.

For every fixture, record:

- source filename/fixture ID;
- source dimensions;
- crop dimensions;
- expected visual orientation;
- EXIF status if known;
- current OpenCV heuristic result;
- Paddle result + confidence;
- Tesseract OSD result + confidence;
- runtime;
- correct/incorrect/uncertain.

The test must be performed on the **same crop bytes** for all orientation candidates so the comparison is fair.

### Acceptance principle

Do not select Paddle, Tesseract, browser logic, or an OpenCV heuristic because it works on one image.

Select a method only after the frozen orientation battery shows it is reliable enough on our real DL types.

If the chosen classifier has a confidence score:

```text
IF confidence is above a threshold proven by our fixture battery
    rotate the actual crop pixels
OR
    do not guess; show the crop for user review
```

The confidence threshold must come from our results, not an arbitrary value copied from the internet.

## One-change-at-a-time implementation plan

When this work resumes, do not combine the entire plan in one patch.

Suggested slices:

1. **Test only** — freeze orientation fixtures and record current behavior. No production change.
2. **Bake-off only** — run current heuristic vs Paddle vs Tesseract on the exact same clean crops. No product behavior change.
3. **Choose orientation authority** from measured results.
4. **Isolate current heuristic** — clearly separate landscape geometry from semantic 180° orientation logic.
5. **Integrate chosen classifier** after clean OpenCV crop only.
6. **Confidence/fallback behavior** — high-confidence rotate; uncertain means no automatic guess.
7. **Preview verification** — confirm user sees physically upright stored pixels.
8. **FRONT OCR fallback** only as its own later slice.
9. **Browser original-byte preservation experiment** only as its own later slice if still justified.
10. Deploy only after frozen DL battery passes; then advance DL gold separately.

## IF / OR summary

```text
IF user uploads a normal photo
OR a WhatsApp/gallery/edited photo
→ browser normalizes it for upload.

IF it is larger than 2400
→ browser downsizes.
OR if smaller
→ browser keeps the size; no intentional upscale.

IF backend source is larger than 1544
→ make a 1544 detector copy.
OR if smaller
→ use its existing size for detection.

IF OpenCV finds valid DL geometry
→ remember rotation + corners.
OR if it cannot confirm geometry
→ existing retry/manual path; orientation classifier is not the fix.

IF geometry succeeds
→ map corners back to the best source pixels and warp from those pixels.

IF the crop is good
→ only then test human-readable orientation.

IF the chosen orientation method is confidently correct
→ physically rotate the crop pixels.
OR if uncertain
→ do not guess; show the user the crop.

IF FRONT is low-resolution but OpenCV crop succeeds
→ do not reject just because it is small; orientation then OCR/manual review.

IF BACK processed PDF417 succeeds
→ use it.
OR if it fails
→ try the stored higher-resolution BACK.
OR if both fail
→ future FRONT OCR/AI/manual fallback.
```

## Architectural lock

The immediate problem is **orientation after a successful crop**.

Do not solve it by simultaneously changing Chrome/browser normalization, OpenCV detection scale, OpenCV corner logic, warp source, OCR, PDF417, Paddle and Tesseract.

First hold crop quality constant. Then compare orientation methods on the same clean crops. Once one method is proven, integrate that one semantic stage without disturbing the gold OpenCV geometry path.
