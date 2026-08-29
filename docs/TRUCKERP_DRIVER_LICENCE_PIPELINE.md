# TruckERP Driver Licence Capture & OpenCV Pipeline

**Project:** TruckERP  
**Scope:** Applicant driver-licence front/back capture, browser normalization, automatic OpenCV localization/confirmation, storage, onboarding UI, tenant-scoped phone companion capture, QR/SMS handoff, real-time synchronization, and future native-app delivery.

## Current frozen implementation checkpoints

### Server OpenCV

`adb87f7d7920d50e253467ab6ee7331af081ea12`  
`fix(dl): add Canny rough locator after HSV failure`

Processor version:

`PREPROCESS_VERSION = "2026-08-29-hsv-canny-rough-v1"`

### Browser normalization

`f00cf96e61438d65f0fe334d59750c45239b0c64`  
`feat(dl): normalize licence images before upload`

### Tenant-scoped resumable phone capture

`67db75d9eeef23b1bb4e90c61a73bf443b0541db`  
`feat(dl): add tenant-scoped resumable licence capture link`

### Applicant Application Page QR phone companion

`32b28531417300cbe8f58343a5061daa3e3ed36d`  
`feat(dl): add QR phone companion to applicant licence step`

These are separate frozen layers. Do not change server geometry while working on QR/SMS, event delivery, guided camera, or native-app integration.

---

## 1. Product model

The existing Applicant Application Page is the control center:

```text
/onboarding?token=<applicant-token>
```

The Driver's License box on that page owns the user-facing licence workflow.

The phone route:

```text
/dl-capture/<opaque-dl-capture-token>
```

is not another onboarding application. It is a temporary, restricted phone companion tied to the same `person_application`.

Approved user story:

```text
Applicant Application Page
        ↓
Driver's License box
        ↓
Upload from this device
        OR
Use your phone
        ↓
QR code now
SMS later
        ↓
Phone captures FRONT then BACK
        ↓
Same person_application updated
        ↓
Laptop reflects fresh application state
        ↓
Continue onboarding
```

---

## 2. End-to-end image-processing flow

```text
Photo selected or captured
        ↓
Browser normalization
(EXIF-aware decode + max 2400px long side + JPEG 0.92)
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

No four confirmed corners means no processed crop.

---

## 3. Browser normalization — implemented

File:

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
DL_UPLOAD_MAX_LONG_SIDE = 2400
DL_UPLOAD_JPEG_QUALITY = 0.92
```

Examples:

```text
3024×4032 → 1800×2400
4032×3024 → 2400×1800
1536×2048 → unchanged dimensions
```

Non-images are passed through unchanged.

Browser may normalize representation and provide capture UI, but it must not become the licence geometry authority.

Do not add browser-side HSV, Canny, perspective correction, manual corner selection, or guide-region cropping.

Proven observations:

```text
IMG_6446 normalized to 1350×2400 → PASS via CANNY
IMG_8788 normalized → PASS via HSV
IMG_8789 → honest FAIL
ed3411 earlier/raw representation → PASS via CANNY
ed3411 normalized representation → PASS via HSV
```

The `ed3411` result is sample-specific evidence; do not generalize that normalization always improves HSV.

---

## 4. Storage and preview contract

### Success

```text
file_id      = source/original upload
enh_file_id  = separate processed JPEG
status       = PROCESSED
processed    = 1000×631 corrected card
```

### Failure

```text
file_id      = source/original upload
enh_file_id  = null / absent
status       = FAILED
processed    = none
```

Never turn a failed OpenCV result into a fake processed image.

Never:

```text
OpenCV FAIL
→ letterbox full source
→ PROCESSED
```

Never:

```text
OpenCV FAIL
→ guessed fallback crop
→ PROCESSED
```

Preview availability and crop status are separate:

```text
PROCESSED → show enhanced preview
FAILED    → show source preview + retry options
```

---

## 5. Server OpenCV architecture

Rough localization order:

```text
1. HSV scene-based locator
2. Canny external-contour locator only after HSV fails
```

Both feed the same existing `_confirm_all_four_corners()` authority.

Canny is a second rough locator, not an independent crop engine.

Server orientation passes:

```text
original
cw90
ccw90
rotate180
```

Do not blindly force phone images to landscape in the browser.

---

## 6. Frozen geometry

HSV morphology:

```text
open 5×5 ellipse
close 19×19 ellipse
```

Rough admission:

```text
normal rough area: 0.06–0.65
close-up rough area: >0.65–1.00
close-up rough ratio: 1.25–1.95
minimum side: 20px
minimum component area ratio: 0.004
```

Four-edge confirmer:

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

Universal per-edge floor:

```text
>= 50 inliers
```

Mode-specific final gates:

```text
normal min edge inliers = 50
close-up min edge inliers = 80
normal polygon area = 0.08–0.65
close-up polygon area <= 0.98
final ratio = 1.25–1.95
max corner angle error <= 20°
corners within source bounds/tolerance
```

Output:

```text
1000×631 JPEG
```

Do not weaken these thresholds merely to force a difficult sample through.

---

## 7. Source-frame rejection

A rectangle that is effectively the photograph boundary is not a licence.

Current margin:

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

`IMG_8789` remains an honest failure and must not be forced through by lowering geometry thresholds.

---

## 8. Current regression expectations

| Sample | Expected | Typical locator in tested representation |
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

OpenCV slice checkpoint:

```text
6 targeted DL tests passed
```

QR/capture slice checkpoint:

```text
10 tests passed in tests/test_dl_capture.py
```

Do not represent unrelated repository DB/socket/syntax failures as DL regressions.

---

## 9. Two-token security model

### Normal applicant token

```text
/onboarding?token=<applicant-token>
```

Authority:

```text
full applicant onboarding application
```

### Restricted phone capture token

```text
/dl-capture/<opaque-token>
```

Authority:

```text
FRONT/BACK driver-licence capture only
```

The QR/SMS handoff must use the restricted capture token, not the full applicant onboarding token.

---

## 10. Tenant-scoped capture token — implemented

Checkpoint: `67db75d9`

Uses existing `application_access_tokens` with:

```text
purpose = dl_capture
token_hash = SHA-256 of raw token
expires_at = 24 hours
revoked_at
completed_at
```

Generation:

```python
raw_token = secrets.token_urlsafe(32)
token_hash = sha256(raw_token)
```

The database stores the hash, not the raw capture token.

Issuing a new capture token revokes only prior active `dl_capture` tokens for the same application. It must not revoke `invite`, `document_resume`, or any other token purpose.

Capture lookup requires:

```text
hostname-resolved tenant_id
+ token_hash
+ purpose = dl_capture
+ revoked_at IS NULL
+ expires_at > now
```

Wrong tenant, unknown token, expired token, or revoked token must show the same generic phone-page experience:

```text
Invalid or expired capture link
```

---

## 11. Capture progress and resume

FRONT/BACK state lives only in the application:

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

The same capture token may be reopened or used from another device and must resume from fresh server-side application state.

After both sides are `PROCESSED`, set `completed_at`; further arbitrary capture uploads are rejected.

---

## 12. QR phone companion — implemented

Checkpoint: `32b28531`

The existing Driver's License section on the Applicant Application Page now supports an explicit **Use your phone** action.

Important behavior:

```text
Application Page loads
→ no capture token is issued

Applicant clicks Use your phone
→ applicant-scoped endpoint authenticates invite token
→ requires invite purpose + DRAFT application
→ derives application_id server-side
→ issues restricted dl_capture token
→ returns tenant HTTPS capture URL
→ Application Page renders QR
```

Applicant endpoint:

```text
POST /api/v1/driver-onboarding/applicant/application/dl-capture-link?token=<applicant-token>
```

The browser does not supply `application_id`.

The existing admin capture-link issuer remains available and shares the same underlying issue logic.

The QR is rendered in-browser with:

```text
react-qr-code@2.0.15
```

No external QR service is used.

QR content is exactly:

```text
https://{tenant-slug}.truckerp.me/dl-capture/<opaque-token>
```

Do not put any PII or the full applicant token in the QR.

No:

```text
applicant name
application_id
licence number
email
phone number
full onboarding token
```

Production capture URLs use the proxy-aware public HTTPS scheme. Nginx explicitly overwrites `X-Forwarded-Proto` with `$scheme` on the API proxy, so client-supplied forwarding headers are not trusted for URL construction.

---

## 13. Application Page phone panel

Current Application Page behavior:

```text
DRIVER'S LICENSE

existing upload-from-this-device controls

──────── OR ────────

Use your phone
[ Use your phone ]
```

After explicit issuance:

```text
Use your phone

[ QR CODE ]

Scan this code with your phone to take or choose
photos of the front and back of your driver licence.

Front: Waiting / Received
Back:  Waiting / Received

[ Check status ]
```

The QR is not generated automatically on page mount or re-render. This avoids silently revoking a capture link already being used on a phone.

The **Check status** button is a temporary/manual fallback only. It performs one fresh application fetch and derives FRONT/BACK status from the database-backed application state.

There is no polling loop and no `setInterval` for this feature.

---

## 14. Phone companion UI

The phone page remains intentionally simple:

```text
Front Driver Licence
[ Take Photo ]
[ Choose Existing Photo ]

        ↓ accepted

Back Driver Licence
[ Take Photo ]
[ Choose Existing Photo ]

        ↓ accepted

✓ Driver licence received
You can return to the other device.
```

Native mobile inputs:

```html
<!-- New photo -->
<input type="file" accept="image/*" capture="environment">

<!-- Existing saved photo -->
<input type="file" accept="image/*">
```

Both paths use the same handler:

```text
File
→ normalizeDlUpload()
→ existing dl_capture upload API
→ existing _apply_applicant_dl_upload()
→ existing OpenCV pipeline
```

No guided camera, `getUserMedia`, live overlay, or automatic shutter is required for ordinary phone capture.

---

## 15. Proven QR companion flow

Live demo verification established:

```text
Phone FRONT IMG_8788
→ PROCESSED via HSV

Laptop manual Check status
→ Front ✓ Received
→ Back waiting

Phone BACK IMG_6446
→ PROCESSED via CANNY

Laptop manual Check status
→ Front ✓ Received
→ Back ✓ Received
→ licence complete
```

The desktop applicant `dl-upload` route also remained `PROCESSED` in regression testing after the shared capture-link/upload changes.

---

## 16. SMS delivery — next delivery channel, not implemented

QR and SMS must use the same restricted HTTPS capture URL:

```text
https://{tenant-slug}.truckerp.me/dl-capture/<opaque-token>
```

SMS must not introduce a different token model or capture protocol.

The mobile number / Send Link feature is intentionally separate from the QR checkpoint.

---

## 17. Real-time synchronization — next architecture slice

Do not make one-second polling the primary design.

Current repo inspection found no implemented onboarding/DL:

```text
SSE
WebSocket
Redis event bus
background worker
PostgreSQL LISTEN/NOTIFY event path
transactional outbox
```

The current **Check status** button is a one-shot refresh only.

Approved future architecture:

```text
phone upload
        ↓
DB/application state commits
        ↓
durable domain event / transactional outbox
        ↓
delivery layer
        ↓
┌──────────────────┬───────────────────┐
│                  │                   │
web browser        iOS/native
SSE today          APNs later
```

The database/application state remains authoritative. Events only signal that something changed.

When the laptop receives a change signal, it should fetch fresh application state once and render from that state.

Suggested transport-independent event names:

```text
driver_licence.front_processed
driver_licence.back_processed
driver_licence.processing_failed
driver_licence.capture_complete
```

Do not encode SSE, Redis, PostgreSQL, or Apple-specific assumptions into the domain event contract.

---

## 18. Transactional outbox direction

Prefer a durable transactional outbox over making `LISTEN/NOTIFY` the permanent source of truth for events.

Desired transaction:

```text
BEGIN

1. save application CDL state
2. insert corresponding domain event into outbox

COMMIT
```

Then a delivery worker/adaptor sends pending events to interested transports.

This prevents a successful application update from permanently losing its notification if an API process crashes immediately afterward.

`LISTEN/NOTIFY` may later be used as a wakeup optimization, but the durable event record should live in the outbox.

---

## 19. Browser delivery direction — SSE

For the Applicant Application Page, SSE is the likely one-way browser transport:

```text
Laptop opens one SSE connection
        ↓
phone commits licence change
        ↓
durable event becomes deliverable
        ↓
SSE signals application changed
        ↓
laptop fetches fresh application once
        ↓
render Front/Back status from DB state
```

SSE is a transport adapter only; business logic must not depend on SSE.

---

## 20. Future native apps / Universal Links

Keep the capture URL as a normal tenant HTTPS URL:

```text
https://{tenant-slug}.truckerp.me/dl-capture/<opaque-token>
```

Future iPhone behavior:

```text
Capture URL opened
        ↓
TruckERP iOS app installed?
   ├─ NO  → mobile web /dl-capture page
   └─ YES → Apple Universal Link opens native app
```

The native app can use the same restricted capture token and the same backend application/upload contract.

Delivery transports may evolve independently:

```text
browser → SSE
iOS     → APNs
Android → platform push
```

The QR/SMS link itself does not change.

---

## 21. Guided camera — optional later enhancement

A custom browser camera is not required for the basic flow.

If normal native-camera/upload attempts repeatedly fail strict OpenCV confirmation, a future guided camera may provide framing assistance.

Possible ID-1 guide ratio:

```text
85.60 / 53.98 ≈ 1.586
```

Possible framing guidance must remain assistance only.

Do not crop to the guide before upload. Submit the full frame and keep server four-edge confirmation as final authority.

Do not add automatic shutter until live framing measurements are empirically proven.

---

## 22. Frozen invariants

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

Do not change frozen geometry without empirical evidence.

---

## 23. Capture token schema deployment

Checkpoint `67db75d9` introduced tenant migration:

```text
e8f9a0b1c2d4_application_access_token_completed_at.py
```

It adds nullable `completed_at` to `application_access_tokens`.

The migration is tenant-generic and must be applied through the normal tenant Alembic process to every tenant DB before enabling capture across tenants.

---

## 24. Development rule

Make one controlled change at a time.

For every slice:

```text
1. report current behavior/infrastructure
2. modify one layer only
3. run the relevant battery
4. verify live/container behavior
5. confirm previous PASS behavior remains intact
6. commit only intended files
7. record the checkpoint
```

Keep these as separate slices unless there is a strong implementation reason to combine them:

```text
server OpenCV geometry
browser normalization
tenant capture token/session
Application Page QR handoff
real-time event/outbox delivery
SMS delivery
guided camera
iOS/Android native clients
```
