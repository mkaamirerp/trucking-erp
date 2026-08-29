# TruckERP Driver Licence Capture & OpenCV Pipeline

**Project:** TruckERP  
**Scope:** Applicant driver-licence front/back capture, browser normalization, automatic OpenCV localization/confirmation, storage, onboarding UI, tenant-scoped phone companion capture, QR/SMS handoff, and future event/iOS delivery architecture.

## Current frozen implementation checkpoints

### Server OpenCV

`adb87f7d7920d50e253467ab6ee7331af081ea12`  
`fix(dl): add Canny rough locator after HSV failure`

Current processor version:

`PREPROCESS_VERSION = "2026-08-29-hsv-canny-rough-v1"`

### Browser normalization

`f00cf96e61438d65f0fe334d59750c45239b0c64`  
`feat(dl): normalize licence images before upload`

### Tenant-scoped resumable phone capture

`67db75d9eeef23b1bb4e90c61a73bf443b0541db`  
`feat(dl): add tenant-scoped resumable licence capture link`

These checkpoints are separate layers. Do not change server geometry while working on browser/mobile handoff, QR/SMS, events, or iOS integration.

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
- Let an applicant upload from the current device or use a phone companion flow.
- Keep the normal onboarding application and the restricted phone-capture link tied to the same `person_application`.
- Keep FRONT/BACK completion in application state, not duplicated into client/session state.
- Support QR and SMS handoff today without preventing future iOS/Android native apps.

---

## 2. End-to-end image-processing flow

```text
Photo selected or captured
        ↓
Browser normalization
(EXIF-aware decode + max 2400px long side + JPEG 0.92)
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

A future guided-camera mode may assist framing after a failed upload, but it must still submit the full camera frame to this same server pipeline. The browser must not become an independent geometry authority.

---

## 3. Browser normalization — implemented

Current normalization helper:

`apps/web/src/lib/normalizeDlUpload.ts`

Behavior for image uploads:

```text
selected File
    ↓
browser-native EXIF-aware decode (`from-image`)
    ↓
preserve decoded pixel orientation
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

Non-images such as PDF are passed through unchanged by the helper.

### Browser responsibilities

Allowed:

- EXIF-aware image decode
- payload resizing
- JPEG re-encode
- immediate preview of what will be uploaded
- camera/file input selection
- future guided-camera assistance

Not allowed:

- HSV
- Canny
- card cropping
- corner selection
- perspective correction
- manual geometry
- treating the guide rectangle as the crop

The browser normalizes representation and payload size. The server decides licence geometry.

### Proven normalization observations

```text
IMG_6446 normalized to 1350×2400 → PASS via CANNY
IMG_8788 normalized → PASS via HSV
IMG_8789 → honest FAIL
```

One useful representation-specific observation:

```text
ed3411 earlier/raw representation → PASS via CANNY
ed3411 normalized representation  → PASS via HSV
```

This is evidence that normalization can help the primary HSV path on a sample; it is not a universal claim that normalization always improves HSV.

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

The desktop applicant upload regression after the shared upload refactor confirmed that the original source remains separate from the enhanced 1000×631 processed image.

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

This remains useful after browser EXIF normalization because EXIF may be absent or incorrect and the card itself may be arbitrarily oriented.

Do not blindly rotate portrait captures to landscape in the browser.

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

Known Canny rescue examples include `IMG_6446` and the earlier/raw representation of `ed3411`.

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

Current expected server behavior:

| Sample | Result | Typical locator in current tested representation |
|---|---|---|
| IMG_6446 | PASS | CANNY |
| ed3411 normalized | PASS | HSV |
| IMG_8789 | FAIL | — |
| IMG_8788 | PASS | HSV |
| IMG_9083 couch | PASS | HSV |
| 03_magenta | PASS | HSV |
| 04_dark | PASS | HSV |
| 05_wood | PASS | HSV |
| IMG_9084 | PASS | HSV |
| closeup_8EF4 | PASS | HSV |
| closeup_59a5 | PASS | HSV |

Targeted server DL pytest checkpoint from the OpenCV slice:

```text
6 passed
```

Capture-link unit checkpoint from the tenant phone-capture slice:

```text
5 passed
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

This is a natural candidate for future guided capture.

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
offer retry / future guided camera
```

---

## 18. Main onboarding Driver's License box — product model

The Driver's License box on the normal applicant onboarding page is the complete user-facing licence workflow.

The applicant should not need to understand separate APIs, tokens, or sessions.

Approved product story:

```text
DRIVER'S LICENSE

Upload from this device
[ Upload / Take Photo ]

──────── OR ────────

Use your phone
[ QR CODE ]

Mobile number: [____________]
[ Send Link ]
```

If the applicant is already on a phone, the current-device controls can use the native camera or the phone's Photos/Gallery picker.

If the applicant is on a laptop/desktop, `Use your phone` creates/uses the restricted tenant-scoped `dl_capture` companion link.

The laptop remains on the onboarding application while the phone captures FRONT and BACK.

The phone companion is not another onboarding application. It is a temporary licence-capture surface attached to the same `person_application`.

---

## 19. Two-token security model

The two token types have deliberately different authority.

### Normal applicant token

```text
/onboarding?token=<applicant-token>
```

Purpose:

```text
full applicant onboarding application
```

### DL capture token

```text
/dl-capture/<opaque-token>
```

Purpose:

```text
restricted FRONT/BACK driver-licence capture only
```

This separation is intentional. A QR code or SMS sent to a phone should not need to expose the token that grants access to the applicant's full onboarding application.

---

## 20. Tenant-scoped capture token — implemented

Implemented by checkpoint `67db75d9` using existing `application_access_tokens`.

Key properties:

```text
purpose = dl_capture
token_hash = SHA-256 of raw token
raw token returned only when link is issued
expires_at = 24-hour initial policy
revoked_at
completed_at
```

Generation uses cryptographically secure randomness:

```python
raw_token = secrets.token_urlsafe(32)
token_hash = sha256(raw_token)
```

The database stores the hash, not the raw capture token.

Issuing a new DL capture link revokes only prior active `dl_capture` tokens for that application. It must not revoke `invite`, `document_resume`, or any other token purpose.

### Tenant validation

Capture lookup is bound to the tenant resolved from the hostname:

```text
request.state.tenant_id
+ token_hash
+ purpose = dl_capture
+ revoked_at IS NULL
+ expires_at > now
```

Wrong tenant, unknown token, expired token, or revoked token must all produce the same generic capture-page experience:

```text
Invalid or expired capture link
```

No cross-tenant token-existence details are shown in the phone UI.

---

## 21. Capture progress and resume behavior — implemented

FRONT/BACK progress is not duplicated into the access-token row.

Source of truth:

```text
person_applications.intake_payload.files.CDL_FRONT.dl_preprocess_status
person_applications.intake_payload.files.CDL_BACK.dl_preprocess_status
```

Resume logic:

```text
FRONT not PROCESSED
→ FRONT

FRONT PROCESSED + BACK not PROCESSED
→ BACK

FRONT PROCESSED + BACK PROCESSED
→ COMPLETE
```

`FAILED` does not count as complete.

The same token may be closed/reopened or opened from another device and must resume from fresh server-side application state.

After both sides are `PROCESSED`, `completed_at` is set and further arbitrary capture uploads are rejected.

One capture token handles both FRONT and BACK.

---

## 22. Phone capture UI

The phone companion should remain intentionally simple:

```text
Driver Licence

Front
[ Take Photo ]
[ Choose Existing Photo ]

        ↓ accepted

Back
[ Take Photo ]
[ Choose Existing Photo ]

        ↓ accepted

✓ Driver licence received
You can close this page.
```

Mobile input behavior:

```html
<!-- Take a new photo -->
<input type="file" accept="image/*" capture="environment">

<!-- Pick an existing saved photo -->
<input type="file" accept="image/*">
```

Both paths must reuse the same handler and the same `normalizeDlUpload()` helper before calling the same capture upload API.

Do not duplicate browser normalization or server OpenCV logic.

A custom `getUserMedia()` guided camera is not required merely to take a phone picture; the native camera input already provides that behavior. A custom camera should be added only if we later need a live overlay, framing assistance, or auto-capture.

---

## 23. QR and SMS handoff — approved next product flow

The laptop Driver's License box can issue one restricted capture URL:

```text
https://{tenant-slug}.truckerp.me/dl-capture/{opaque-token}
```

That exact URL is used by both delivery methods:

```text
QR code → encodes capture URL
SMS     → sends capture URL
```

QR requires no external delivery provider and should be implemented/tested first.

SMS later adds only a delivery provider; it must not create a different capture protocol or token model.

No PII should be placed directly in the URL. Do not include applicant name, licence number, application ID, email, or phone number in the path/query.

---

## 24. Laptop companion behavior

The laptop stays on the normal onboarding application while the phone works.

Example UI progression:

```text
Use your phone

[ QR CODE ]

Front: Waiting...
Back:  Waiting...
```

After the phone uploads FRONT successfully:

```text
Front: ✓ Received
Back:  Waiting...
```

After BACK succeeds:

```text
Front: ✓ Received
Back:  ✓ Received

✓ Driver licence received

[ Continue ]
```

Both browser sessions operate on the same `person_application`; there is no direct phone-to-laptop connection.

```text
PHONE ───────→ SERVER ←─────── LAPTOP
   uploads               receives change signal
```

The laptop must always render completion from fresh server state, not from an event payload alone.

---

## 25. Real-time synchronization — future-proof architecture

Do not make one-second polling the primary design.

Also do not make a specific browser transport such as SSE the business architecture.

The durable architecture is:

```text
Application state changes
        ↓
DOMAIN EVENT
        ↓
Event delivery layer
        ↓
┌───────────────┬───────────────┬────────────────┐
│               │               │                │
Web browser     iOS app         Android/future
SSE today       APNs later      push/other
```

### Database remains the source of truth

Events only signal that something changed.

Example:

```text
Phone upload
    ↓
OpenCV PASS
    ↓
DB commits CDL_FRONT = PROCESSED
    ↓
domain event emitted
    ↓
laptop receives event
    ↓
laptop fetches application once
    ↓
render Front ✓ from DB state
```

Never use an event message itself as proof that the licence is complete.

### Suggested event names

Transport-independent domain names:

```text
driver_licence.front_processed
driver_licence.back_processed
driver_licence.processing_failed
driver_licence.capture_complete
```

The event contract should not contain assumptions about SSE, Apple Push Notifications, Redis, or PostgreSQL.

---

## 26. Durable event delivery / transactional outbox — planned

For a future-proof production event layer, prefer a transactional outbox over making PostgreSQL `LISTEN/NOTIFY` the permanent source of events.

Desired transaction:

```text
BEGIN

1. save CDL_FRONT/CLD_BACK application state
2. insert corresponding domain event into outbox

COMMIT
```

Then an event worker delivers pending events to interested transports.

This prevents a successful licence DB update from permanently losing its notification if an API process crashes immediately afterward.

`LISTEN/NOTIFY` may still be used as an optimization/wakeup mechanism, but the durable event record should live in the outbox.

---

## 27. Web delivery today — SSE planned

For the laptop browser, Server-Sent Events are a good one-way transport:

```text
Laptop opens one SSE connection
        ↓
server waits
        ↓
phone commits licence change
        ↓
domain event delivered
        ↓
SSE tells laptop application changed
        ↓
laptop fetches fresh application once
```

This avoids aggressive one-second polling while keeping the browser implementation simple.

SSE is a transport adapter only. Business logic must not depend on it.

A conservative low-frequency reconnect/fallback strategy may be added for degraded-network conditions, but tight polling is not the primary path.

---

## 28. Future iOS app / Universal Link

The capture URL must remain an ordinary tenant HTTPS URL:

```text
https://{tenant-slug}.truckerp.me/dl-capture/{opaque-token}
```

This allows the same QR code and SMS format to survive a future native app launch.

Future iPhone behavior can become:

```text
Capture URL opened on iPhone
        ↓
TruckERP iOS app installed?
   ├─ NO  → mobile web /dl-capture page
   └─ YES → Apple Universal Link opens TruckERP iOS app
```

The native app then uses the same restricted capture token and the same backend DL upload/application APIs.

The QR code and SMS sender do not need to know whether the destination is web or native.

Future client delivery can use:

```text
browser → SSE
iOS     → APNs
Android → platform push
```

while all clients consume the same domain/application state model.

---

## 29. Guided mobile camera — optional later enhancement

A custom browser camera is not necessary for the basic phone flow.

If normal native-camera/upload attempts fail OpenCV confirmation, a future guided camera may provide an ID-1-shaped guide.

ID-1 aspect ratio:

```text
85.60 / 53.98 ≈ 1.586
```

Possible target framing:

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
```

Important invariants:

- the guide is assistance only;
- do not crop to the guide rectangle before upload;
- submit the full camera frame;
- server four-edge confirmation remains final authority;
- auto-capture should not be added until framing measurements are empirically proven.

---

## 30. Frozen invariants

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

## 31. Separation of responsibilities

### Main onboarding browser

```text
full applicant application
Driver's License box
upload from current device
issue/show phone companion QR/SMS link
reflect fresh application state
Continue when FRONT + BACK are PROCESSED
```

### Phone web/native client

```text
restricted dl_capture token
FRONT/BACK capture or existing-photo selection
normalize payload (web)
upload to same backend
show success/failure
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

### Storage/application state

```text
preserve source
store enhanced separately only on success
FRONT/BACK PROCESSED state is authoritative
```

### Event layer

```text
business/application commit
→ durable domain event/outbox
→ browser SSE / future APNs / other transports
```

---

## 32. Important checkpoints

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

Browser normalization:

```text
f00cf96e61438d65f0fe334d59750c45239b0c64
feat(dl): normalize licence images before upload
```

Tenant-scoped resumable phone capture:

```text
67db75d9eeef23b1bb4e90c61a73bf443b0541db
feat(dl): add tenant-scoped resumable licence capture link
```

Treat these as frozen layer checkpoints for subsequent QR/SMS, event delivery, guided camera, and native-app work.

---

## 33. Deployment note for capture token schema

Capture checkpoint `67db75d9` introduced tenant migration:

```text
e8f9a0b1c2d4_application_access_token_completed_at.py
```

It adds nullable `completed_at` to `application_access_tokens`.

The migration is tenant-generic and must be applied through the normal tenant Alembic upgrade process for every tenant DB before enabling the capture feature across tenants.

---

## 34. Development rule

Make one controlled change at a time.

For every slice:

```text
1. report current behavior
2. modify one layer only
3. run the relevant known battery
4. verify live/container behavior
5. confirm no previous PASS regressed
6. commit only intended files
7. record the new checkpoint
```

Keep these as separate slices unless there is a strong implementation reason to combine them:

```text
server OpenCV geometry
browser normalization
tenant capture token/session
main-page QR handoff
SMS delivery
real-time event/outbox delivery
guided camera
iOS/Android native clients
```
