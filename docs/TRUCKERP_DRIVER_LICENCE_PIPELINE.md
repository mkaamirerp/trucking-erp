# TruckERP Driver Licence Capture & OpenCV Pipeline

**Project:** TruckERP  
**Scope:** Applicant driver-licence front/back capture, upload, preprocessing, automatic card localization, four-edge confirmation, perspective correction, storage, preview, browser normalization, and planned guided mobile capture.

## Current frozen server baseline

`adb87f7d7920d50e253467ab6ee7331af081ea12`  
`fix(dl): add Canny rough locator after HSV failure`

Current processor version:

`PREPROCESS_VERSION = "2026-08-29-hsv-canny-rough-v1"`

---

## 1. Core design goals

The driver-licence pipeline must:

- Accept ordinary real-world phone photos.
- Work with tilt, perspective, varied backgrounds, and card position when geometry can be proved.
- Preserve the uploaded source image.
- Produce a separate corrected 1000×631 processed image only after geometry confirms the card.
- Never mark a failed crop as a successful processed licence.
- Never use a guessed crop.
- Keep the existing four-edge confirmer as the final authority.
- Show the uploaded picture even when automatic processing fails.
- Offer guided mobile capture when an uploaded photo cannot be confirmed.

---

## 2. End-to-end upload flow

```text
Existing photo selected
        ↓
Browser normalization
(EXIF-aware decode + max 2400px long side)
        ↓
Upload normalized source
        ↓
Persist source/original
        ↓
Server OpenCV
        ↓
HSV rough locator
        ↓
existing four-edge confirmer
        ↓
PASS?
 ├─ YES → perspective warp → 1000×631 → save enh_file_id
 │
 └─ NO
      ↓
   Canny external-contour rough locator
      ↓
   existing four-edge confirmer
      ↓
   PASS?
    ├─ YES → perspective warp → 1000×631 → save enh_file_id
    └─ NO  → FAILED, keep original, no enh_file_id
```

Future failure path:

```text
Upload fails four-edge confirmation
        ↓
show original photo
        ↓
offer "Take Guided Photo"
        ↓
phone camera with ID-card guide
        ↓
same server OpenCV pipeline
```

---

## 3. Browser upload path

Current UI call chain:

```text
DLUploadStep.handleFileSelect(side, File)
  ↓
OnboardingApplicantPage.handleDlUploadSide
  ↓
uploadDl(docType, file)
  ↓
api.uploadPersonApplicationDlFile({ file })
  ↓
FormData:
  - doc_type
  - file
  ↓
POST /driver-onboarding/applicant/application/dl-upload
```

### Planned browser normalization

For image uploads only:

```text
selected File
    ↓
browser-native EXIF-aware decode
    ↓
preserve resulting pixel orientation
    ↓
resize proportionally to max long side 2400px
    ↓
never upscale
    ↓
JPEG encode quality 0.92
    ↓
upload normalized File
```

Constants:

```ts
const DL_UPLOAD_MAX_LONG_SIDE = 2400;
const DL_UPLOAD_JPEG_QUALITY = 0.92;
```

Resize formula:

```ts
const scale = Math.min(
  1,
  DL_UPLOAD_MAX_LONG_SIDE / Math.max(width, height),
);
```

Examples:

```text
3024×4032 → 1800×2400
4032×3024 → 2400×1800
1536×2048 → unchanged dimensions
```

### Browser responsibilities

Allowed:

- EXIF-aware image decode
- payload resizing
- JPEG re-encode
- immediate preview of what will be uploaded
- future guided-camera assistance

Not allowed:

- HSV
- Canny
- card cropping
- corner selection
- perspective correction
- manual geometry

The browser reduces ambiguity and payload size. The server decides licence geometry.

---

## 4. Storage contract

### OpenCV success

```text
file_id      = source/original upload
enh_file_id  = separate processed JPEG
status       = PROCESSED
processed    = 1000×631 corrected card
```

### OpenCV failure

```text
file_id      = source/original upload
enh_file_id  = null / absent
status       = FAILED
processed    = none
```

Never:

```text
OpenCV FAIL
→ letterbox full photo
→ mark PROCESSED
```

Never:

```text
OpenCV FAIL
→ alternate guessed crop
→ mark successful
```

---

## 5. Preview contract

Crop status and preview availability are separate.

### Successful crop

```text
status = PROCESSED
preview = enh_file_id
UI = READY
```

### Failed crop

```text
status = FAILED
preview = original file_id
UI = retry / guided capture
```

A failed crop must not make the uploaded image disappear.

---

## 6. OpenCV architecture

Two rough-localization strategies are used in order:

```text
1. HSV scene-based locator
2. Canny external-contour locator
```

Both feed the same existing four-edge confirmation engine.

Canny is not a second crop engine. It only proposes a rough card location.

---

## 7. Server orientation handling

The processor tests:

```text
original
cw90
ccw90
rotate180
```

This remains useful even after browser EXIF normalization because EXIF may be absent or incorrect and the card itself may be arbitrarily oriented.

---

## 8. HSV scene preflight

The HSV classifier describes the scene/background, not card geometry.

Sample the outer ~12% border and compute:

```text
s50
s75
v25
v50
v75
```

Scene family:

```text
if s50 < 55:
    if v50 < 85:
        NEUTRAL_DARK
    elif v50 < 170:
        NEUTRAL_MID
    else:
        NEUTRAL_LIGHT
else:
    CHROMATIC
```

### Masks

NEUTRAL_DARK:

```text
H 35–135
S >= 30
V low = max(90, min(160, v50 + 25))
```

NEUTRAL_MID:

```text
H 35–135
S >= 40
V low = max(120, min(185, v50 + 30))
```

NEUTRAL_LIGHT:

```text
H 35–135
S low = max(35, min(90, s75 + 12))
V >= 60
```

CHROMATIC:

```text
H 35–135
S >= 25
V >= 60
```

Secondary strict-cool:

```text
H 35–135
S >= 40
V >= 60
```

Legacy-cool:

```text
H 35–135
S >= 18
V >= 60
```

Morphology:

```text
open 5×5 ellipse
close 19×19 ellipse
```

Candidate generation:

```text
minimum component area ratio = 0.004
top components = up to 6
minimum side = 20px
normal rough area = 0.06–0.65
close-up rough area = 0.65–1.00 with rough ratio 1.25–1.95
```

Candidate score:

```text
ratio_error * 4 - density * 0.6
```

---

## 9. Guarded close-up mode

Normal mode:

```text
rough area: 0.06–0.65
confirmed polygon area: 0.08–0.65
minimum final edge inliers: 50
```

Close-up admission:

```text
0.65 < rough area <= 1.00
and
1.25 <= rough ratio <= 1.95
```

Close-up confirmation:

```text
confirmed polygon area <= 0.98
minimum final edge inliers >= 80
```

A universal per-edge floor of 50 still applies before the stricter close-up aggregate test.

---

## 10. Canny external-contour rough locator

Added at:

`adb87f7d fix(dl): add Canny rough locator after HSV failure`

Canny runs only after HSV fails to confirm a card.

Conceptual flow:

```text
grayscale
  ↓
blur
  ↓
Canny
  ↓
validated minimal morphology
  ↓
external contours
  ↓
cv2.minAreaRect
  ↓
cv2.boxPoints
  ↓
ordered rough corners
  ↓
source-frame rejection
  ↓
existing _confirm_all_four_corners()
```

Proven rescues:

```text
IMG_6446 → PASS via CANNY
ed3411   → PASS via CANNY
```

Existing HSV successes remain HSV successes.

---

## 11. Source-frame rejection

A detected rectangle that is effectively the photograph boundary is not a licence.

Current rule:

```text
SOURCE_FRAME_MARGIN_PX = 8
```

Reject as `SOURCE_FRAME_CANDIDATE` when:

```python
min_x <= 8
and min_y <= 8
and max_x >= width - 8
and max_y >= height - 8
```

Example:

```text
IMG_8789
legacy_cool
area ≈ 99.8%
touches all four image boundaries
→ SOURCE_FRAME_CANDIDATE
→ reject
```

---

## 12. Four-edge confirmation engine

The existing confirmer is the sole acceptance authority.

Frozen geometry:

```text
Gaussian blur = 5×5
Sobel kernel = 3
edge sample range = 8%–92%
edge sample count = 180
winner score = gradient - 0.6 * abs(offset)
minimum gradient = 25
RANSAC distance = 4.5px
RANSAC iterations = 400
RNG seed = 123
```

For each proposed edge:

```text
rough edge
  ↓
sample along edge
  ↓
search normal to rough edge
  ↓
choose strongest gradient evidence
  ↓
RANSAC
  ↓
cv2.fitLine
```

All four fitted lines are required.

No four confirmed edges = no crop.

---

## 13. Final geometry gates

Acceptance requires:

- all four edge lines;
- valid line intersections;
- corners within source bounds/tolerance;
- mode-specific polygon area;
- final card ratio between 1.25 and 1.95;
- max angle error <= 20°;
- required edge inliers.

Normal:

```text
minimum edge inliers >= 50
```

Close-up:

```text
universal per-edge floor >= 50
final close-up minimum edge inliers >= 80
```

No threshold should be weakened merely to force a difficult sample through.

---

## 14. Perspective warp

After confirmation only:

```text
confirmed TL/TR/BR/BL
        ↓
perspective transform
        ↓
corrected licence
        ↓
1000×631 JPEG
```

The processed image is stored separately as `enh_file_id`.

---

## 15. Regression battery

Current expected server results:

| Sample | Result | Locator |
|---|---|---|
| IMG_6446 | PASS | CANNY |
| ed3411 | PASS | CANNY |
| IMG_8789 | FAIL | — |
| IMG_8788 | PASS | HSV |
| IMG_9083 couch | PASS | HSV |
| 03_magenta | PASS | HSV |
| 04_dark | PASS | HSV |
| 05_wood | PASS | HSV |
| IMG_9084 | PASS | HSV |
| closeup_8EF4 | PASS | HSV |
| closeup_59a5 | PASS | HSV |

Current targeted DL pytest checkpoint:

```text
6 passed
```

Unrelated repository DB/socket failures or unrelated syntax/test failures must not be reported as DL regressions.

---

## 16. Known difficult case: IMG_8789

`IMG_8789` remains an honest failure.

Canny can propose a near-full-bleed candidate:

```text
rough area ≈ 0.897
rough ratio ≈ 1.530
close-up mode = true
```

Edge evidence:

```text
[159, 53, 82, 47]
```

The universal edge floor fails on one side before close-up confirmation can succeed.

Correct result:

```text
FAILED
```

Do not lower thresholds just to accept this image.

This is a natural candidate for guided mobile capture.

---

## 17. Existing-upload acceptance threshold

Do not use an arbitrary confidence percentage.

The acceptance threshold is:

```text
FOUR_CORNERS_CONFIRMED
```

Flow:

```text
HSV
 ↓ fail
Canny
 ↓
existing four-edge confirmer
```

If confirmed:

```text
accept
show corrected preview
READY
```

If not confirmed:

```text
show source preview
FAILED
offer guided camera
```

---

## 18. Guided mobile camera — planned

When existing-upload processing fails:

```text
We couldn't clearly detect all four edges.

[ Take Guided Photo ]
```

The phone camera will show an ID-1-shaped guide.

ID-1 aspect ratio:

```text
85.60 / 53.98 ≈ 1.586
```

Suggested capture target:

```text
ideal card width:    70–75% of frame
acceptable range:    60–80%
auto-capture range:  approximately 65–78%
```

Keep visible background around all four edges. Avoid full-bleed capture.

Possible guidance:

```text
Too far       → Move closer
Too close     → Move farther away
Outside guide → Fit all four corners
Too tilted    → Hold phone straighter
Motion        → Hold steady
Too dark      → More light
Good frame    → auto capture after brief stability
```

These signals assist capture only. Final acceptance remains server-side.

---

## 19. Tenant-based mobile capture link — planned

Production URL form:

```text
https://{tenant-slug}.truckerp.me/dl-capture/{opaque-token}
```

Example:

```text
https://demo.truckerp.me/dl-capture/<opaque-token>
```

Do not place applicant names, licence numbers, application IDs, or other PII directly in the URL.

---

## 20. Capture token behavior — planned

The token is a secure resume key for the capture session.

It should resolve server-side to at least:

```text
tenant_id
application_id
purpose = DRIVER_LICENCE_CAPTURE
expires_at
status
created_at
completed_at
revoked_at
```

Validate:

```text
hostname tenant == token tenant
token active
token not expired
token not revoked
```

A token for Tenant A must never work on Tenant B's hostname.

---

## 21. Resume behavior

Progress must be server-side, not browser-local.

Each visit:

```text
token
 ↓
validate tenant + token
 ↓
load application
 ↓
inspect CDL_FRONT / CDL_BACK state
 ↓
resume first incomplete side
```

Examples:

```text
Front complete + Back missing
→ resume Back

Front failed
→ resume Front

Front complete + Back failed
→ resume Back
```

Token lifecycle:

```text
ACTIVE
  ↓
IN_PROGRESS
  ↓
COMPLETE
```

Do not consume the token after the first upload.

One token handles both front and back.

---

## 22. Mobile capture UI — planned

```text
Driver Licence

FRONT
[ Take Photo ]
[ Upload Existing Photo ]

BACK
[ Take Photo ]
[ Upload Existing Photo ]
```

After both are accepted:

```text
✓ Driver licence received
```

The same server applicant DL processing/storage pipeline must be reused.

Do not create a separate geometry engine for mobile capture.

---

## 23. Delivery methods — planned

The tenant-bound capture URL can later be delivered through:

```text
SMS
email
QR code
WhatsApp
copy link
```

An office user can begin onboarding on desktop while the applicant completes licence capture on a phone.

---

## 24. Frozen invariants

Do not reintroduce:

- manual corner selection into automatic processing;
- geometry classifier experiments;
- guessed crop;
- rough-box crop fallback;
- alternate back-only geometry;
- EDGE_WARP fallback;
- STORAGE_NORMALIZE fake success;
- relaxed back-side thresholds;
- Canny as an independent crop engine;
- source-frame candidates as valid cards;
- arbitrary confidence replacing four-edge confirmation.

Do not change without empirical evidence:

```text
gradient threshold = 25
RANSAC distance = 4.5px
RANSAC iterations = 400
RNG seed = 123
normal min edge inliers = 50
close-up min edge inliers = 80
ratio gate = 1.25–1.95
max angle error = 20°
normal polygon max = 0.65
close-up polygon max = 0.98
```

---

## 25. Separation of responsibilities

### Browser

```text
EXIF-aware decode
max-2400 payload normalization
preview
future guided-camera assistance
```

### Server rough localization

```text
HSV first
Canny second
```

### Server final geometry

```text
Sobel
RANSAC
fitLine
four intersections
strict confirmation gates
```

### Server output

```text
perspective warp
1000×631
separate enhanced file
```

### Storage

```text
preserve source
store enhanced separately only on success
```

### UI

```text
success → enhanced preview
failure → source preview + retry/guided capture
```

---

## 26. Important checkpoints

HSV adaptive scene seed:

```text
b6618bd2
fix(dl): adapt HSV seed to scene background
```

Guarded close-up:

```text
6257a70b
fix(dl): allow guarded close-up licence photos above 65% area
```

HSV-first + Canny-second:

```text
adb87f7d7920d50e253467ab6ee7331af081ea12
fix(dl): add Canny rough locator after HSV failure
```

Treat `adb87f7d` as the current frozen server OpenCV baseline for future browser and guided-capture work.

---

## 27. Development rule

Make one controlled change at a time.

For every slice:

```text
1. report current behavior
2. modify one layer only
3. run known image battery
4. verify live/container behavior
5. confirm no previous PASS regressed
6. commit only intended files
7. record the new checkpoint
```

Browser normalization, guided camera, tenant capture token/session, and SMS delivery are separate slices from server OpenCV geometry.
