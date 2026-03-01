# DL Upload + Onboarding — Full Spec (Authoritative)

This document is the **single source of truth** for driver license upload, extraction, prefill, and applicant onboarding. It is compiled from the exact conversation/spec provided; do not summarize or assume.

---

## 1. DL Upload Button Behavior (Front/Back) — Parse → Extract → Prefill

### 1.1 User taps Upload DL Front

**UI immediately:**
- File picker (accept: jpg/png/heic/pdf)
- After selection, show a card:
  - Status: **Uploading…** → **Scanning…**
  - Progress spinner
  - "We're reading your license and filling the form."

**Backend immediately:**
- Save file (storage_key, sha256…)
- Create/replace PersonApplicationFile for doc_type=CDL_FRONT (**old active becomes is_active=false** — *later corrected to: old DL is **discarded**, see below*)
- Kick off extraction job right away

### 1.2 Extraction job runs automatically

- Reads the uploaded file
- Extracts structured fields into a normalized payload shape (dl_extract_v1)
- Writes:
  - `PersonApplicationFile.extract_payload = { …dl_extract_v1… }`
  - `PersonApplication.intake_payload["dl_extract"]` = { merged normalized fields }
  - `PersonApplication.intake_payload["dl_extract_status"]` = PENDING | OK | FAILED
  - `PersonApplication.intake_payload["dl_extract_confidence"]` = overall score + per-field scores

### 1.3 When extraction completes → Prefill the form

**UI behavior:**
- Form fields auto-fill (no user typing needed)
- Every prefilled field shows a subtle tag: **"From DL"** + confidence (High/Med/Low)
- If a field is low confidence or ambiguous: highlight it and require user confirmation (simple "Confirm" check or just a visible warning)

### 1.4 Upload DL Back (optional but supported)

- Same flow, doc_type=CDL_BACK
- Back side extraction can add/confirm: endorsements, restrictions, class, address, etc.
- If front/back disagree: show "Conflict detected" and prefer the higher-confidence value, but let user choose.

### 1.5 "Replace file" behavior — CORRECTION (locked)

**If new DL is loaded then old DL is DISCARDED.**

- **Discard** means:
  - Delete old DB row(s) for that doc_type
  - Delete the old file from storage (local/S3)
  - Replace with the new one
  - Re-run extraction
  - Update prefill
- **Do not** keep old file as is_active=false for audit in v1; delete row + delete file.
- Prefill updates **do not overwrite** fields the user manually edited unless they click **"Apply DL values"**.

---

## 2. Must-Have UX Rules

- Do **not** block the user while scanning: they can continue the form; fields fill when ready.
- Show **3 states** clearly: **Uploading → Scanning → Filled** (or Failed).
- If failed: show "Couldn't read the license. Try a clearer photo or enter manually." and provide **Retry extraction** button.
- Manual entry always allowed; no dead end.

---

## 3. API Contract (Minimal)

- **POST /person-applications/{id}/files** (multipart)  
  - doc_type = CDL_FRONT | CDL_BACK  
  - Returns: file_id, status = "PENDING_EXTRACT"  
  - *Later locked for v1: same request returns **final** status (sync extraction); no PENDING in response.*

- **GET /person-applications/{id}** (or /extraction-status)  
  - Returns: dl_extract_status, merged extracted fields, per-field confidence.

- **POST /person-applications/{id}/files/{file_id}/reextract**  
  - Re-runs extraction.

### Field overwrite rule (important)

- When extraction returns: if field is **empty** → fill it.
- If **user already edited it** → do **not** overwrite, unless user clicks **"Apply DL values"**.
- This prevents "I corrected it and it changed back" frustration.

---

## 4. Data Model Expectations

**PersonApplication**
- id, tenant_id, status, intake_payload (JSON) — holds merged extracted fields + UI state.

**PersonApplicationFile**
- id, tenant_id, application_id, doc_type, storage_key, original_filename, content_type, size_bytes, sha256, uploaded_at, extract_payload (JSON).

---

## 5. Upload Handler Behavior (Code-Like Spec)

**Endpoint:** `POST /api/v1/person-applications/{app_id}/dl-files`  
**Content-Type:** multipart/form-data  
**Fields:** doc_type = CDL_FRONT | CDL_BACK, file = &lt;binary&gt;, source = "laptop" | "phone" (optional)

```
function upload_dl_file(tenant_id, app_id, doc_type, file):
  assert doc_type in {CDL_FRONT, CDL_BACK}
  app = db.get(PersonApplication, tenant_id=tenant_id, id=app_id)
  assert app exists
  assert app.status in APPLICATION_STATUS_ALLOW_UPLOAD  # DRAFT, optionally SUBMITTED

  # 1) DISCARD any previous file for same side
  old_files = db.query(PersonApplicationFile)
    .where(tenant_id==tenant_id, application_id==app_id, doc_type==doc_type)
    .all()
  for each old in old_files:
    storage.delete(old.storage_key)   # discard file bytes
    db.delete(old)                    # discard row
  db.flush()

  # 2) Save new file to storage
  stored = storage.save_onboarding_license(file, tenant_id, app_id, doc_type)

  # 3) Insert new record
  rec = PersonApplicationFile(...stored..., extract_payload=null)
  db.add(rec)
  db.flush()

  # 4) Mark extraction pending on application
  app.intake_payload["dl_extract_status"] = "PENDING"
  app.intake_payload["dl_extract_error"] = null
  app.intake_payload["dl_extract_last_uploaded_doc_type"] = doc_type
  app.intake_payload["dl_extract_last_file_id"] = rec.id
  db.commit()

  # 5) Trigger extraction immediately (sync or async)
  enqueue_extract_job(tenant_id, app_id, rec.id)

  return { file_id: rec.id, status: "PENDING", doc_type: doc_type }
```

---

## 6. dl_extract_v1 Shape (Locked)

```json
{
  "version": "dl_extract_v1",
  "doc_type": "CDL_FRONT",
  "overall_confidence": 0.92,
  "fields": {
    "first_name": { "value": "John", "confidence": 0.95 },
    "last_name": { "value": "Smith", "confidence": 0.95 },
    "dob": { "value": "1990-01-01", "confidence": 0.88 },
    "license_number": { "value": "D1234567", "confidence": 0.90 },
    "issuing_state": { "value": "ON", "confidence": 0.99 },
    "expiry_date": { "value": "2028-05-01", "confidence": 0.93 },
    "address": { "value": "123 Main St, Toronto, ON", "confidence": 0.80 },
    "class": { "value": "AZ", "confidence": 0.87 },
    "endorsements": { "value": "Air Brake", "confidence": 0.75 },
    "restrictions": { "value": "", "confidence": 0.70 }
  }
}
```

---

## 7. Merge Rule (Locked) — Don't Overwrite User Edits

```
if user_edited_fields[field] == true:
  do not overwrite
else:
  overwrite (or fill if empty)
```

**Field source tracking:**
```json
"field_sources": {
  "first_name": { "source": "DL", "confidence": 0.95, "doc_type": "CDL_FRONT" }
}
```

---

## 8. Field Mapping (Must Be Explicit) — Extract → Intake Key

| EXTRACT FIELD   | INTAKE KEY        |
|-----------------|-------------------|
| first_name      | intake_payload["first_name"] |
| last_name       | intake_payload["last_name"] |
| dob             | intake_payload["date_of_birth"] |
| license_number  | intake_payload["license_number"] |
| issuing_state   | intake_payload["license_state"] |
| expiry_date     | intake_payload["license_expiry"] |
| address         | intake_payload["address_line"] |
| class           | intake_payload["license_class"] |
| endorsements    | intake_payload["endorsements"] |
| restrictions    | intake_payload["restrictions"] |

Put mapping inside merge function; do not scatter.

---

## 9. Architecture Lock v1 — Synchronous Extraction (Final)

- **No background job in v1.** Extraction runs **inside the same HTTP request** as upload.
- **Flow:** discard old → save file → run dl_extract_stub() → merge into intake_payload → commit → return **final** state (file_id, dl_extract_status, intake_payload).
- No Celery, worker, queue, async job. No "PENDING" in response for same request.
- **Reextract:** `POST .../files/{file_id}/reextract` also runs synchronously; returns updated state.
- **Polling** is only for **phone upload scenario** (laptop polls GET person-applications/{appId} every 2s until updated_at/dl_extract_status/file list changes).

---

## 10. Routes and API Paths (Final Decisions)

- **Applicant onboarding:** `/onboarding?token=...` — only entry; no /laptop/ prefix.
- **Scan page (laptop):** `/onboarding/scan?token=...`
- **Mobile scan:** `/m/scan/:token` — that token is **scan-session token**, not onboarding token.
- **API path:** Use **/person-applications/{appId}**; do NOT extend /driver-onboarding/.... appId == PersonApplication.id.
- **Old endpoint:** `POST /driver-onboarding/submissions/{id}/license-upload` → **deprecated**. Return **410 Gone** with message: `"Deprecated. Use POST /api/v1/person-applications/{id}/dl-files"`.

---

## 11. Platform DB vs Tenant DB (Control-Plane Rule)

- **Platform DB:** resolve token → (tenant_id, application_id, expires, status) **only**. No PersonApplication, no intake_payload, no DL files.
- **Tenant DB:** fetch PersonApplication, save files, merge, extract, storage keys — **all** application data.
- **Applicant tenant:** must come from **onboarding token**, not from host/subdomain. Implement `resolve_onboarding_token(token)` using platform DB; then route logic uses `get_tenant_db(tenant_id)` for all reads/writes.
- **Resolver:** small service (e.g. `app/services/onboarding_token_resolver.py`) uses platform DB only; returns (tenant_id, application_id) or raises 401/410. No platform session in applicant router beyond the resolver.

---

## 12. Scan Session (When Implemented)

- **ScanSession** table must live in **tenant DB** (tenant_id, application_id, token, expires_at). Token resolves inside tenant DB only; no platform DB.
- **Phone** never sees tenant; only scan-session token. Tenant resolved server-side only.
- **Scanic** (or community scanner): install only when implementing /m/scan/:token (Phase 5). Do not install before Phase 1 is stable. Verify real Scanic npm API before finalizing mobile page.

---

## 13. Applicant UX Contract (DL First Flow)

- **Entry:** Invite link lands at `/onboarding?token=...`. First screen: title "Complete your driver onboarding", subtitle "Let's start by reading your driver license." Primary: [ Start with my license ]. Secondary: "Enter details manually".
- **States (per side):** IDLE → UPLOADING → SCANNING → SUCCESS | FAILED. One spinner; message swap at 600ms: "Uploading your license…" then "Reading your license and filling the form…".
- **SUCCESS:** "Done. We've filled the form from your license." Scroll to form. Fields show [From DL] + optional High/Med/Low.
- **FAILED:** "We couldn't read the license." [ Try again ] [ Enter manually ].
- **Replace:** "Replacing previous license…" then same state machine. No "discard/delete" in UI.
- **Tone:** No "extraction", "payload", "dl_extract_status", "Confidence score 0.87". Use "Reading", "Filling", "Try again", "Enter manually".
- **From DL tag:** Render from field_sources[field] when user_edited_fields[field] !== true. If user edits, hide tag immediately (no server round-trip).
- **Scan with phone:** Show only on desktop (e.g. `window.matchMedia("(pointer:fine)").matches`). Not on phone.

---

## 14. Naming and State Rules

- Call it **application**, not submission (UI + code). application = PersonApplication.
- **State placement:** Page-level state in OnboardingApplicantPage: step, application, userEditedFields. DLUploadStep owns per-side dlState only.
- **DL state mapping (sync):** `dlOk = resp.dl_extract_status === "OK"; setDlState(dlOk ? "SUCCESS" : "FAILED");` — no PENDING in v1.
- **Apply license values again (optional):** If present, Option A = reextract and overwrite only non-edited fields; or skip in v1.

---

## 15. Implementation Order (Phases)

1. **Phase 1:** Backend discard-old + upload endpoint + **synchronous** extraction (stub) + merge; GET returns intake_payload; reextract endpoint. Frontend: /onboarding entry + DL upload + prefill + "From DL" tags + spinner + submit.
2. **Phase 2:** Phone scan session (backend); polling on laptop scan page.
3. **Phase 3:** Laptop "Scan with phone" UI (QR + link).
4. **Phase 4:** Mobile scan page /m/scan/:token (camera + scan + upload).
5. **Phase 5:** Install Scanic (or chosen scanner); verify API; wire into mobile page.

Do not build phone scan / Scanic until Phase 1 is complete and stable.

---

## 16. Invite Link and Token Policy

- **Invite link TTL:** 60 days from creation (expires_at = now + 60 days).
- **Invalidation:** On **APPROVE** or **REJECT** of the application, invalidate all onboarding tokens for that application immediately (delete rows or set expires_at = now()). Link must not work after decision.
- **Token storage:** Onboarding token lookup may live in platform DB for resolution only (token → tenant_id, application_id). Application data and files only in tenant DB.

---

## 17. Audit Script

A script `tools/dl_onboarding_audit.sh` (or equivalent) should verify:
- Git state and key files (dl_merge.py, person_applications router, dl_extract_stub, storage delete).
- Router uses tenant DB for business data; platform only for token resolution.
- Deprecation route returns 410 with full path message.
- Platform DB has no business tables (person_applications, etc.); tenant DB has PersonApplication tables. ScanSession (if any) in tenant DB only.
- Optional: live API checks with ONBOARDING_TOKEN and APP_ID.

---

*End of spec. When implementing, follow this document; do not rely on summarized or assumed behavior.*
