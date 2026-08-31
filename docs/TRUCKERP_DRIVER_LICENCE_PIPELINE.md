# TruckERP Driver Licence Capture & OpenCV Pipeline

**Project:** TruckERP  
**Last updated:** 2026-08-30  
**Scope:** Applicant driver-licence front/back capture, upload, browser normalization, tenant-bound phone handoff, guided mobile capture, server OpenCV confirmation, PDF417 extraction, storage, preview, and onboarding hydration.

---

## 1. Current checkpoint

Current synchronized DL branch before guided-camera implementation:

```text
dl-opencv-clean
HEAD dd41e09bee0d633c7a7819bc597cb40cf65c9143
fix(dl): stabilize phone capture link lifecycle
```

Current frozen server processor version:

```text
PREPROCESS_VERSION = "2026-08-29-hsv-canny-rough-v1"
```

The frozen server OpenCV geometry authority was established at:

```text
adb87f7d7920d50e253467ab6ee7331af081ea12
fix(dl): add Canny rough locator after HSV failure
```

Later DL commits add browser normalization, resumable phone capture, QR companion, realtime sync, 1544 validation, purge/reset behavior, onboarding theme alignment, and capture-link lifecycle stabilization without replacing the frozen server geometry authority.

---

## 2. Non-negotiable image-size contract

These three sizes have different jobs and must not be collapsed:

```text
2400 px long side = browser ingestion/storage ceiling
1544 px long side = server OpenCV working-copy ceiling
1000 x 631        = final confirmed rectified licence output
```

Rules:

- Browser normalization may reduce an uploaded/captured image to a maximum long side of 2400.
- The normalized source/original is persisted.
- Server OpenCV makes a temporary EXIF-normalized working copy.
- Only the working copy is reduced to 1544 when needed.
- The stored source must not be overwritten by the 1544 working copy.
- A processed 1000×631 image is produced only after all four edges are confirmed.

---

## 3. Core design goals

The DL pipeline must:

- accept ordinary real-world phone photos;
- work with tilt, perspective, varied backgrounds, and card position when geometry can be proved;
- preserve the normalized source image;
- produce a separate corrected 1000×631 processed image only after geometry confirms the card;
- never mark a failed crop as successful;
- never use a guessed crop;
- keep the existing four-edge confirmer as final authority;
- show the uploaded source when processing fails;
- provide a secure phone handoff from the desktop onboarding page;
- guide the phone user toward a high-quality photograph;
- automatically capture a good frame when the browser guidance is satisfied;
- keep manual photo and existing-photo fallbacks;
- keep browser guidance advisory and server acceptance authoritative.

---

## 4. Current end-to-end server pipeline

```text
browser source photo
        ↓
normalizeDlUpload()
EXIF-aware decode + max 2400 long side
        ↓
upload normalized source
        ↓
persist source/original
        ↓
make temporary EXIF-normalized server working copy
        ↓
if long side >1544, scale WORKING COPY only
        ↓
HSV rough proposal
        ↓
_confirm_all_four_corners()
        ↓
confirmed?
 ├─ YES → warp confirmed card → 1000×631
 │          ↓
 │       persist processed/enhanced image
 │
 └─ NO
      ↓
   Canny rough proposals
      ↓
   same _confirm_all_four_corners()
      ↓
   confirmed?
    ├─ YES → warp confirmed card → 1000×631
    └─ NO  → FAILED, preserve source, no fake enhanced image
```

Back-side success then continues through:

```text
processed back image
        ↓
PDF417 decode
        ↓
structured fields
        ↓
merge into intake
        ↓
onboarding form hydration + SSE refresh
```

---

## 5. Browser upload path

Current desktop upload call chain:

```text
DLUploadStep.handleFileSelect(side, File)
  ↓
normalizeDlUpload(file)
  ↓
OnboardingApplicantPage.handleDlUploadSide
  ↓
uploadPersonApplicationDlFile(...)
  ↓
POST /api/v1/driver-onboarding/applicant/application/dl-upload
```

Current browser normalization constants:

```text
DL_UPLOAD_MAX_LONG_SIDE = 2400
DL_UPLOAD_JPEG_QUALITY   = 0.92
```

Browser normalization:

```text
selected/captured File
    ↓
browser-native EXIF-aware decode
    ↓
resize proportionally to max long side 2400
    ↓
never upscale
    ↓
JPEG encode
    ↓
upload normalized File
```

---

## 6. Browser responsibilities

The browser is allowed to:

- perform EXIF-aware decode;
- resize payloads to the 2400 ceiling;
- JPEG re-encode;
- show immediate local previews;
- operate the live phone camera;
- perform low-resolution advisory document detection;
- coach the user with move closer / move farther / center / straighten / hold still / lighting guidance;
- decide when a frame is good enough to fire the camera;
- automatically capture a high-resolution still;
- fall back to manual photo or existing-photo selection.

The browser is **not** allowed to:

- become the final licence-geometry authority;
- mark a licence `PROCESSED` itself;
- persist an advisory browser crop as the authoritative processed licence;
- bypass the server four-edge confirmer;
- replace the frozen Python OpenCV detector;
- overwrite the normalized stored source with a smaller analysis frame;
- introduce a second independent crop engine.

Browser guidance answers:

```text
"Is this a good time to take the picture?"
```

The server answers:

```text
"Were all four licence edges actually confirmed?"
```

The server wins.

---

## 7. Storage contract

### Success

```text
file_id      = normalized source/original upload
enh_file_id  = separate processed JPEG
status       = PROCESSED
processed    = 1000×631 corrected card
```

### Failure

```text
file_id      = normalized source/original upload
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

## 8. Preview contract

Crop status and preview availability are separate.

Success:

```text
status  = PROCESSED
preview = processed/enhanced file
UI      = READY / RECEIVED
```

Failure:

```text
status  = FAILED
preview = source/original file
UI      = retry / guided capture
```

A failed crop must not make the uploaded image disappear.

---

## 9. Server OpenCV architecture

Two rough-localization strategies run in order:

```text
1. HSV scene-based rough locator
2. Canny external-contour rough locator
```

Both feed the same final authority:

```text
_confirm_all_four_corners()
```

Canny is not a second crop engine. It proposes a rough card location only.

---

## 10. Frozen server orientation and geometry

The processor tests:

```text
original
cw90
ccw90
rotate180
```

Frozen confirmation geometry includes:

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

Normal acceptance:

```text
rough area                    0.06–0.65
confirmed polygon area        0.08–0.65
minimum edge inliers          50
```

Guarded close-up admission:

```text
0.65 < rough area <= 1.00
1.25 <= rough ratio <= 1.95
```

Guarded close-up confirmation:

```text
confirmed polygon area <= 0.98
universal per-edge floor >= 50
final close-up min inliers >= 80
```

Final geometry gates also require:

- all four fitted lines;
- valid line intersections;
- corners within source bounds/tolerance;
- final card ratio between 1.25 and 1.95;
- max angle error <= 20°;
- required edge inliers.

No four confirmed edges = no crop.

---

## 11. Source-frame rejection

A rectangle that is effectively the photograph boundary is not a licence.

Current rule:

```text
SOURCE_FRAME_MARGIN_PX = 8
```

Reject a source-frame candidate when all four sides touch the image boundary within that margin.

This protects against accepting a nearly full-frame photograph as if the photograph itself were the card.

---

## 12. 1544 working-scale decision — frozen

The 1544 server working scale is not a cosmetic optimization. It is load-bearing for known production behavior.

Controlled A/B evidence included IMG_6446:

```text
1544 working copy:
HSV NO_CONFIRM
Canny CONFIRMED
output 1000×631
PDF417 PASS

browser-normalized 2400 direct to detector:
HSV NO_CONFIRM
Canny NO_CONFIRM
FOUR_CORNERS_NOT_CONFIRMED
```

Direct 2400 also increased processing time and memory without improving known successful samples.

Therefore:

```text
2400 = ingestion/storage ceiling
1544 = validated OpenCV operating scale
```

Do not remove the 1544 working scale unless the detector is deliberately redesigned and the frozen battery is rerun.

Freeze checkpoint after history replay:

```text
07a8b09a test(dl): freeze validated 1544 OpenCV working scale
```

Original pre-replay SHA:

```text
2128deece84a2b2614a22aea701bd01d922ef7e5
```

---

## 13. Regression battery

Expected server results include:

| Sample | Result | Locator |
|---|---|---|
| IMG_6446 | PASS | CANNY |
| ed3411 | PASS | HSV at validated 1544 production path |
| IMG_8789 | FAIL | — |
| IMG_8788 | PASS | HSV |
| IMG_9083 couch | PASS | HSV |
| 03_magenta | PASS | HSV |
| 04_dark | PASS | HSV |
| 05_wood | PASS | HSV |
| IMG_9084 | PASS | HSV |
| closeup_8EF4 | PASS | HSV |
| closeup_59a5 | PASS | HSV |

Private real-DL regression fixture remains outside all Git worktrees.

Recent validated tests:

```text
13 OpenCV tests passed with private fixture
4 purge tests passed
17 combined tests passed
```

No real licence fixture may be committed.

---

## 14. Known difficult case: IMG_8789

IMG_8789 remains an honest failure.

The server must not weaken thresholds merely to force this photo through.

This is exactly the kind of case guided mobile capture is meant to improve by helping the user take a better source image rather than weakening server acceptance.

---

## 15. Current tenant-bound phone capture infrastructure

Implemented phone-handoff architecture:

```text
applicant onboarding step 0
        ↓
issue restricted dl_capture link
        ↓
https://{tenant-host}/dl-capture/<opaque-token>
        ↓
DlCapturePage
        ↓
front upload
        ↓
same server DL processing pipeline
        ↓
back upload
        ↓
same server DL processing pipeline + PDF417
```

Current React route:

```text
/dl-capture/:token
```

The URL must not contain:

- applicant name;
- licence number;
- application ID;
- tenant ID;
- other PII.

Only the opaque restricted token appears in the path.

---

## 16. Capture-token authority

Current capture purpose:

```text
dl_capture
```

Current TTL:

```text
24 hours
```

Current behavior:

- capture tokens are tenant-scoped;
- raw token is returned only when issued;
- persisted token material is hash-based;
- a new capture link revokes the prior active `dl_capture` token for the same application;
- invite/document-resume tokens are separate and are not revoked by DL capture issuance;
- one capture token handles both front and back;
- session progress is resolved server-side from the application state;
- old revoked links return invalid/expired behavior;
- current design keeps at most one active `dl_capture` token per application.

Do not create a second token authority for QR, email, or guided camera.

All handoff methods must point to the same currently-active restricted capture session.

---

## 17. Current phone-capture page status

The current `DlCapturePage` is a functional foundation, not the finished guided-camera experience.

Currently implemented:

```text
restricted capture route
session loading/resume
Take Photo
Choose Existing Photo
normalizeDlUpload <=2400
front upload
back upload
server PROCESS/FAIL response
front → back progression
complete state
```

Not yet considered finished:

```text
live getUserMedia camera
DL-shaped overlay
move closer / move farther guidance
centering guidance
tilt guidance
motion/stability guidance
light/blur guidance
automatic shutter
```

The guided-camera work below is the next feature layer on top of the existing secure capture/session transport.

---

## 18. Phone handoff channels — frozen product decision

Supported handoff channels:

```text
QR code
Copy link
Open capture on current device
Email capture link
```

Not supported in this slice:

```text
SMS
phone-number input
WhatsApp
new messaging vendor
```

The current disabled "Send link via text" placeholder is not a finished feature and must not remain as a fake production control.

---

## 19. Email capture-link contract

The onboarding invite is created by an admin and the applicant email is already stored on:

```text
PersonApplication.email
```

Therefore the DL card must **not** ask the applicant to type an email address again.

Email behavior:

1. applicant is already authenticated to the onboarding application through the invite flow;
2. backend validates the current application and DRIVER workflow;
3. backend uses the existing DL capture-link issuance helper;
4. prior active `dl_capture` token is revoked;
5. one new restricted capture token is issued;
6. the restricted `/dl-capture/<token>` URL is emailed to `PersonApplication.email` using existing SMTP infrastructure;
7. the same new capture URL is returned to the browser;
8. QR, Copy link, Open capture, and emailed URL all reference the same active token.

If `PersonApplication.email` is absent:

```text
No applicant email is available for this application.
```

Do not:

- ask the applicant for another email;
- email the main onboarding invite token as the capture token;
- add a new mail vendor;
- add SMS;
- log raw capture tokens or full token-bearing capture URLs.

---

## 20. QR / copy / open UX contract

### QR

Generating:

```text
Preparing QR code…
```

Success:

```text
render QR for the current restricted capture link
```

Failure:

```text
Could not create the phone capture link.
[ Retry QR ]
```

Capture-link issuance failure must not be silently swallowed.

### Copy link

When a restricted capture link exists:

```text
[ Copy link ]
```

Copy only the restricted `/dl-capture/...` URL.

Show short success feedback such as:

```text
Copied
```

### Open capture

A desktop `window.open()` opens the capture page on the current device. It does not transfer a page to another phone.

Use truthful wording such as:

```text
Open capture
```

or:

```text
Open on this device
```

---

## 21. Guided mobile camera — target experience

The finished normal phone flow is:

```text
open restricted capture link
        ↓
request rear camera
        ↓
show live camera + ID-1 guide
        ↓
low-resolution advisory document analysis
        ↓
show one live instruction
        ↓
card becomes aligned + sharp + stable
        ↓
"Perfect — hold still"
        ↓
automatic high-resolution capture
        ↓
normalize captured still <=2400
        ↓
existing capture upload API
        ↓
server OpenCV <=1544 working copy
        ↓
same four-edge confirmer
        ↓
PROCESSED?
 ├─ YES front → "Front accepted" → Flip licence → guide BACK
 ├─ YES back  → COMPLETE
 └─ NO        → resume camera with server retry message
```

Normal success should not require the user to tap a shutter button.

Manual capture remains available as a fallback.

---

## 22. Camera API

Use browser media APIs:

```text
navigator.mediaDevices.getUserMedia()
```

Prefer the rear camera:

```text
facingMode: { ideal: "environment" }
width:  { ideal: 1920 }
height: { ideal: 1080 }
```

These are preferences, not exact requirements.

The live `<video>` should be compatible with mobile browsers:

```text
autoPlay
playsInline
muted
```

Camera permission denial or unsupported `getUserMedia` must fall back cleanly to manual controls.

---

## 23. ID-1 guide overlay

Standard ID-1 card dimensions:

```text
85.60 mm × 53.98 mm
aspect ratio ≈ 1.586
```

The phone camera shows a centered DL-shaped guide.

Initial calibration target:

```text
guide width:                 about 70–75% of visible camera width
acceptable card width:       roughly 60–80%
initial auto-capture range:  roughly 65–78%
```

These are starting calibration values, not frozen production thresholds.

Keep visible background around all four card edges.

Guide state may use:

```text
neutral → gray
nearly ready → orange
ready → green
```

The guide is instructional only. It does not crop or confirm the persisted licence.

---

## 24. Browser CV technology decision

For the guided-camera layer, use a locally installed/pinned browser OpenCV.js/WASM implementation when technically practical.

Use it only for low-resolution advisory analysis.

Do **not** use as the production authority:

- jscanify;
- BlinkID;
- Scandit;
- Dynamsoft SDK;
- cloud OCR;
- remote CDN-hosted CV scripts;
- an AI/ML document model;
- a browser-side replacement for the Python detector.

Commercial/document-scanner systems are useful architecture references, not dependencies for this slice.

If a chosen OpenCV.js package causes unacceptable global-bundle impact, licensing problems, or cannot be isolated to the capture route, stop and review the dependency rather than silently introducing another CV stack.

---

## 25. High-resolution source vs low-resolution analysis

The live camera has two distinct data paths.

### Advisory analysis path

```text
video frame
  ↓
downscale to analysis canvas
  ↓
max analysis dimension approximately 640–720 px
  ↓
rough document / quality analysis
```

### Actual upload path

```text
high-resolution camera frame/still
  ↓
File/Blob
  ↓
normalizeDlUpload()
  ↓
max long side <=2400
  ↓
existing capture API
```

Never upload the low-resolution analysis canvas as the normal source just because it was used for guidance.

---

## 26. Browser analysis scheduling

Do not run heavy CV on every 30/60 FPS full-resolution video frame.

Preferred scheduling:

```text
requestVideoFrameCallback()
```

with a safe fallback where unavailable.

Target advisory analysis rate:

```text
approximately 6–10 analyses per second
```

Only one detector operation may run at a time.

No overlapping OpenCV analyses.

---

## 27. Advisory detector

A lightweight browser detector may use:

```text
analysis canvas
  ↓
grayscale
  ↓
small blur
  ↓
Canny/edges
  ↓
contours
  ↓
polygon approximation
  ↓
convex 4-point candidate
  ↓
rank plausible ID-card quadrilateral
```

Useful advisory metrics:

- quadrilateral exists;
- approximate aspect ratio;
- quad width/area relative to frame;
- center offset from guide;
- corners near frame boundary;
- perspective distortion;
- luminance;
- sharpness;
- frame-to-frame movement.

The advisory quad must not become the persisted authoritative crop.

---

## 28. Guided capture state machine

Use explicit internal states.

Recommended set:

```text
CAMERA_STARTING
NO_CARD
TOO_FAR
TOO_CLOSE
NOT_CENTERED
TOO_TILTED
TOO_DARK
TOO_BRIGHT
GLARE
BLURRY
MOVING
HOLD_STILL
READY
CAPTURING
UPLOADING
SERVER_RETRY
COMPLETE
```

User-facing messages should be simple and singular.

Examples:

```text
NO_CARD      → Place your licence inside the frame
TOO_FAR      → Move closer
TOO_CLOSE    → Move farther away
NOT_CENTERED → Center your licence
TOO_TILTED   → Hold your phone straight
TOO_DARK     → Move to better light
GLARE        → Tilt slightly to reduce glare
BLURRY       → Hold steady
MOVING       → Hold still
READY        → Perfect — hold still
```

Do not show several conflicting instructions at once.

Use a deterministic priority order for the highest-value correction.

---

## 29. Blur, light, glare, and tilt

### Blur

A lightweight sharpness metric such as variance of Laplacian may be used on the low-resolution card ROI.

The threshold must be a named calibration constant.

### Lighting

Use simple luminance statistics to identify gross:

```text
TOO_DARK
TOO_BRIGHT
```

Do not add an ML lighting model.

### Glare

Start with a conservative heuristic such as excessive clustered near-white/high-luminance pixels inside the detected card ROI.

Until empirically validated, glare should remain advisory and should not become a noisy single-point blocker of every auto capture.

### Tilt / perspective

Use advisory quad geometry to detect excessive:

- center offset;
- side-to-side perspective;
- opposite-side length imbalance;
- top/bottom edge angle;
- corner proximity to the camera boundary.

Do not perspective-correct the authoritative source in the browser.

---

## 30. Temporal stability and auto capture

Auto capture must not fire from one lucky frame.

Track consecutive good detections using metrics such as:

```text
quad IoU
centroid movement
area change
```

Initial calibration starting points:

```text
IoU >= approximately 0.85
area change <= approximately 15%
3–5 consecutive good analyses
stable interval roughly 350–500 ms
```

These are starting values only.

They must remain named/configurable until calibrated on real devices and licence samples.

When the frame stays good long enough:

```text
READY
→ Perfect — hold still
→ capture lock
→ automatic still capture
```

A capture lock must prevent repeated uploads from the same stable interval.

---

## 31. High-quality still capture

Feature-detect browser still-capture capabilities.

`ImageCapture` may be used when available and reliable, but it must not be required.

Fallback:

```text
current high-resolution video frame
  ↓
full-resolution canvas
  ↓
Blob/File
```

Then always use the existing:

```text
normalizeDlUpload()
```

before upload.

The low-resolution advisory canvas must not be used as the default uploaded source.

---

## 32. Front-to-back progression

Capture session remains server source of truth.

### Front

```text
FRONT
→ guided capture
→ server PROCESSED
→ Front accepted ✓
→ Flip your licence
```

### Back

```text
BACK
→ guided capture
→ server PROCESSED
→ PDF417 extraction
→ COMPLETE
```

Completion:

```text
✓ Driver licence received
```

When complete, stop camera tracks and analysis work.

---

## 33. Server rejection after browser READY

The browser may believe a frame is ready while the server still rejects it.

Correct behavior:

```text
browser READY
→ auto capture
→ upload
→ server FOUR_CORNERS_NOT_CONFIRMED
→ resume live camera
→ show: "We couldn't confirm all four edges. Try again."
```

Do not weaken server thresholds to match the browser's opinion.

Do not fabricate success.

---

## 34. Manual fallbacks

Even after guided auto capture exists, retain:

```text
Take Photo Manually
Choose Existing Photo
```

Fallbacks are required for:

- unsupported browser;
- permission denial;
- unusual licence/background;
- older devices;
- accessibility;
- browser CV initialization failure;
- repeated auto-detector difficulty.

Both manual paths still use:

```text
normalizeDlUpload <=2400
→ same server DL processing pipeline
```

---

## 35. Camera and WASM cleanup

Stop all `MediaStream` tracks when:

- component unmounts;
- token becomes invalid;
- capture completes;
- guided camera is abandoned;
- fatal camera error occurs.

Also cancel:

- video-frame callbacks;
- timers;
- pending analysis loop state.

Release/delete all OpenCV.js/WASM Mats and temporary objects.

Do not leak camera access or browser CV memory.

---

## 36. Mobile/desktop visual language

DL phone capture belongs to the same onboarding product.

Use the current onboarding visual source of truth:

```text
bg-gray-900
cards bg-gray-800/60
border-gray-700/600
orange-400/500
gray secondary
green success
rose error
compact rounded-xl/lg controls
uppercase tracked labels where already used
```

Do not create or preserve a separate `--trk-*` mini-theme for the guided page.

---

## 37. Realtime desktop sync

Phone capture updates the same application state as desktop upload.

Desktop refresh path:

```text
capture upload
  ↓
application/intake update
  ↓
durable domain event/outbox
  ↓
SSE application_changed
  ↓
refresh application
  ↓
update DL state/previews/fields
```

Manual `Check status` remains a fallback if an SSE event is missed.

---

## 38. Continue gate

The applicant cannot continue from License Upload until:

```text
front state == SUCCESS
back state == SUCCESS
license number nonblank
license region nonblank
license expiry nonblank
class nonblank
```

Desktop upload and phone completion must feed the same gate.

---

## 39. Draft reset and purge

Reset must remove both metadata and stored DL files for the exact application only.

Current replayed checkpoint:

```text
2b2db18e fix(dl): purge stored licence files on draft reset
```

Original SHA:

```text
dea6af1965ab337fa386253fb14f5f37a91062dd
```

Deletion must remain exact-path/exact-prefix and must not affect neighboring application IDs or other tenants.

---

## 40. Frozen rejected paths

Do not reintroduce:

- geometry classifier experiments as final authority;
- manual browser corner selection into automatic processing;
- manual fallback crop as automatic success;
- EDGE_WARP independent crop authority;
- STORAGE_NORMALIZE second persistent image truth;
- source-as-card acceptance;
- relaxed corner hacks;
- Canny bypassing `_confirm_all_four_corners()`;
- fake enhanced image on failure;
- browser advisory quad as persisted authoritative crop;
- direct 2400 server detection as replacement for validated 1544 behavior;
- remote CDN CV dependencies without an explicit architecture decision;
- SMS placeholder controls without an SMS service.

---

## 41. What to use / what not to use for guided capture

### Use

```text
getUserMedia
rear-camera preference
requestVideoFrameCallback when available
locally installed/pinned OpenCV.js/WASM for advisory analysis
low-resolution analysis canvas
high-resolution capture source
named calibration constants
temporal stability
capture lock
existing normalizeDlUpload
existing restricted capture session
existing Python server authority
existing SMTP for applicant-email delivery
```

### Do not use

```text
jscanify as production authority
BlinkID SDK
Scandit SDK
Dynamsoft SDK
cloud OCR for camera guidance
new AI model
remote CDN OpenCV
browser authoritative perspective warp
new token system
new SMS vendor
new email input on applicant DL card
```

---

## 42. Separation of responsibilities

### Desktop onboarding UI

```text
upload front/back
QR handoff
copy restricted link
open restricted link
email restricted link to stored applicant email
show realtime phone progress
Continue gate
```

### Phone browser

```text
restricted session
camera lifecycle
ID-1 overlay
advisory CV
live guidance
auto shutter
manual fallback
normalize <=2400
upload
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
confirmed perspective warp
1000×631
separate enhanced file
PDF417 on processed back
intake merge
```

### Storage

```text
preserve source
store enhanced separately only on success
purge exact application folder/prefix on draft reset
```

---

## 43. Guided-camera calibration rule

The first browser guidance thresholds are **not** frozen production rules.

They must be calibrated against real mobile devices and scenes.

At minimum test:

```text
iPhone Safari
Android Chrome
desktop Chrome webcam when useful
```

Scene battery:

```text
too far
too close
off-center
tilted
shaky
dark
bright/glare
good lighting
busy background
front
flip to back
server rejection/retry
permission denied
refresh/reopen token
QR scan
emailed capture link
```

Only after evidence should the browser guidance thresholds be frozen.

This calibration does not weaken or replace the frozen server acceptance thresholds.

---

## 44. Important current checkpoints

Server HSV/Canny authority:

```text
adb87f7d7920d50e253467ab6ee7331af081ea12
fix(dl): add Canny rough locator after HSV failure
```

Browser normalization after history replay:

```text
a992517c feat(dl): normalize licence images before upload
```

Restricted resumable capture link:

```text
9efbca95 feat(dl): add tenant-scoped resumable licence capture link
```

QR phone companion:

```text
ca27e80a feat(dl): add QR phone companion to applicant licence step
```

Realtime licence sync:

```text
d0a3aa63 feat(dl): add realtime licence sync with durable outbox
```

Validated 1544 working scale:

```text
07a8b09a test(dl): freeze validated 1544 OpenCV working scale
```

Draft-reset purge:

```text
2b2db18e fix(dl): purge stored licence files on draft reset
```

Onboarding theme alignment:

```text
2a4ca3ae feat(dl): align licence onboarding with application theme
```

Phone capture-link lifecycle:

```text
dd41e09b fix(dl): stabilize phone capture link lifecycle
```

---

## 45. Development rule

Make controlled slices and preserve evidence.

For each DL slice:

```text
1. report current behavior
2. identify exact layer being changed
3. preserve frozen server authority unless the task is explicitly a detector redesign
4. run focused tests
5. run the known DL battery when server behavior changes
6. verify browser/device behavior when camera behavior changes
7. verify no previous known PASS regressed
8. commit only intended files
9. record the checkpoint in this document
10. deploy only after explicit approval
```

Guided browser camera, QR/copy/email handoff, server OpenCV geometry, authentication, Turnstile, and unrelated onboarding work must remain separate concerns unless a specific change requires an interface between them.
