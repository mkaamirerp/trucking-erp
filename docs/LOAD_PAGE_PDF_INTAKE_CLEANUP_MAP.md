# Load page / PDF / intake — cleanup & contract map (working doc)

This document maps routes, API contracts, and **manual create vs parse hydration** so cleanup can be done in safe slices. **No code changes are implied** by this file alone.

---

## Manual entry bug — symptoms (repro context)

- **Symptom A:** Manual entry did not fill **expected** load details (user expectation vs what appeared after save or after a PDF step).
- **Symptom B:** One test run created **11 empty stops** (or 11 stop rows with no useful address/identity in the UI).

The sections below name **concrete code paths and root-cause candidates** (multiple may apply).

---

## Manual entry — root-cause candidates (with file / function / line)

### 1) “Not filled” — PDF hydration is conditional; several load fields are never set from `extracted`

**Where:** `onParseWorkspacePdf` in `apps/web/src/pages/LoadWorkspacePage.tsx` (roughly 634–746).

- Scalar fields are applied with **“only if present”** guards, e.g. `if (ex.mode?.trim())`, `if (ex.rate != null)`, etc. If the parse returns null/empty for a field, the form **keeps prior manual state** (or initial defaults) — that can look like “PDF didn’t fill” when the model/heuristic under-filled.
- **Hazmat** (`hazmat` / `setHazmat`) is **not** set anywhere in `onParseWorkspacePdf` (no `ex.*` mapping). Only `hydrateFromLoad` sets it from a saved `Load` (462–502). So a user expecting hazmat from PDF will **never** see it from parse in the current code.
- **Pallet/case count**, **customs broker id**, **driver/truck/trailer** are likewise **not** mapped from the parse DTO in this handler; they only come from the user or from `hydrateFromLoad` after a server load exists.

**Why this matters for “manual”:** A user on `/loads/new` may still upload a PDF; the form is `workspaceMode === "manual"` (325–333, 311–333). The lack of field coverage is easy to misread as “manual create broke” if the test mixed manual typing + PDF.

### 2) “11 empty stops” — parse can emit many stop *shells*; the UI filter is “any substantive string,” not “user-visible full address”

**Backend heuristics always append a stop row** when a line matches pickup/delivery markers, even if address fields stay null (`_parse_stops` append at 374–388 in `app/services/load_document_parse.py`).

**Frontend gating** uses `filterMeaningfulParsedStops` / `isMeaningfulParsedStop` in `apps/web/src/loadWorkspace/loadParseStops.ts` (11–28): a stop counts as “meaningful” if **any** of `facility_name`, `street`, `city`, `state_or_province`, `postal_code`, `country`, `reference_number`, `appointment_*`, or `notes` is non-empty after trim.

**Candidate:** A noisy PDF can produce **many** lines that match pickup/delivery regex, and for each block the heuristics may still set e.g. **state** or **date/time** (339–346, 330–332 in `load_document_parse.py`). That can pass `isMeaningfulParsedStop` while the row still *looks* “empty” in the main stop cards (e.g. only a fragment).

**Effect:** `extractedStopsToDraft` in `LoadWorkspacePage.tsx` (261–291) then builds one `DraftStop` per retained parse stop. On save, `buildLoadPersistPayload` (`apps/web/src/loadWorkspace/loadWorkspaceShared.ts` 369–436) serializes **every** draft row via `stopToPayload` (200–216) **without** dropping “all-NULL” operational rows. The API persists **N** `LoadStop` rows for **N** entries (`app/services/loads.py` 176–181 create, 413–423 update). So **11 parse-derived shells that passed the “meaningful” test become 11 persisted stops**.

### 3) No second line of defense on create — default manual stops (2) vs parse replace

**Default for manual new load:** `useState` initializer sets `draftStops` to `initialManualCreateStops()` when `isManual` (375–377), implemented as `[newDraftStop(0,"PICKUP"), newDraftStop(1,"DELIVERY")]` in `loadWorkspaceShared.ts` (251–254).

**After PDF:** If `filterMeaningfulParsedStops(ex.stops ?? []).length > 0`, the code **replaces** the entire draft with `extractedStopsToDraft(meaningfulStops)` (722–725 in `LoadWorkspacePage.tsx`). If that list is long (e.g. 11), the user’s prior two default rows are **gone** — by design, but it amplifies any parse noise.

**If** `meaningfulStops.length === 0`, draft stops are **not** reset by parse; the user keeps the two default empty pickups/deliveries (still two rows, not eleven).

**Conclusion for “11 empties”:** The count **11** strongly suggests **a PDF parse** (or a non-default draft list) + **permissive meaningful filter** + **no server-side empty-stop pruning** — not the default 2-row manual template alone.

### 4) Stale / leaking parse state — limited evidence for *cross-navigation* leak

There is **no** `useEffect` that re-seeds `draftStops` when the route is `/loads/new` beyond the **initial** `useState` (375–377). When `workspaceMode === "manual"`, the large data `useEffect` (755–818) only loads reference lists; it does **not** call `setDraftStops`. So a clean remount of `LoadWorkspacePage` on `/loads/new` should get `initialManualCreateStops()`.

**Residual risk:** If the app ever reuses the same component instance when switching routes without unmounting (atypical in current `App.tsx` where `/loads/new` and `/loads/:id` are separate `Route` entries), in-memory `draftStops` could theoretically persist. **Not observed in the current route table** (see section 1). React Router normally remounts when switching between these paths.

**Intake / linked load** paths load `getLoad` + `hydrateFromLoad` (787–800), which **does** set `setDraftStops(stopsToDraft(l.stops))` (513) — that state reflects **server** stops, not a prior manual session.

### 5) Backend does not coalesce or reject empty `LoadStopCreate` rows

`LoadCreate` / `LoadUpdate` accept `stops` as optional sequences (`app/schemas/load.py` 109–110, 122–153). The service **persists every submitted stop** (176–181, 413–423 in `app/services/loads.py`). There is **no** “drop row if all address fields null” check at write time. Root cause for “too many empty DB rows” can be **client payload shape** alone.

### 6) Load Lab / critical v1.1 — not the same as workspace `POST /loads/parse-document`

Workspace uses **`parseLoadWorkspaceDocument`** → `POST /api/v1/loads/parse-document` → `parse_load_workspace_from_pdf_bytes` in `app/services/load_document_parse.py` (returns legacy/heuristic `LoadDocumentParseResponse`).

**Load Lab** stores **`parse_response`** on `LoadLabExtractionRun` (`app/models/load_lab.py` 50–51; `app/schemas/load_lab.py` 34–35) and is exposed under **`/api/v1/load-lab/...`** (`app/routers/load_lab.py`). That pipeline can produce a **TruckERP-shaped** candidate similar to `LoadDocumentParseResponse`, but **the production web app does not mount a `/loads/lab` route** (no matches under `apps/web` for `load-lab` / Load Lab page). It is a **separate API surface** for experiments and review tooling.

**Critical extraction v1.1** is a different JSON shape (see `docs/critical_extraction_output.v1.1.json` and `app/services/critical_extraction_v11_map.py`); mapping to `LoadParseExtractedFields` is for lab/semantic bridges, not for the browser’s `parse-document` call today.

---

## 1. Full route / page map (frontend)

| Route | Component file | Role |
|--------|----------------|------|
| `/loads` | `apps/web/src/pages/LoadsListPage.tsx` | Paged list of loads; entry to open a load. |
| `/loads/new` | `apps/web/src/pages/LoadWorkspacePage.tsx` | **Manual create** — `isManual` true (`LoadWorkspacePage.tsx` 311–318); `workspaceMode` `"manual"`; initial `draftStops` from `initialManualCreateStops()`. |
| `/loads/:id` | `apps/web/src/pages/LoadWorkspacePage.tsx` | **Edit existing load**; `getLoad` + `hydrateFromLoad` (`755–818`, `462–514`). Optional **dispatch** context: `?dispatchAssign=1` (`337–339`). Optional **intake** context: `?intakeThread=<id>` for email side panel + intake mode (`318–333`). Query `mode=payroll` / `mode=audit` changes sections (`324–333`, `loadWorkspaceShared.ts` `SECTION_CONFIG`). |
| `/loads/lab` | *(absent)* | **No** dedicated Load Lab page in the web app; Load Lab is API-only under `/api/v1/load-lab/...`. |
| `/inbox` and `/intake` | `apps/web/src/pages/LoadInboxPage.tsx` (both paths in `App.tsx` 167–180) | Email thread queues; **navigate to** `OPS.LOAD_WORKSPACE_INTAKE(loadId, threadId)` = `/loads/:id?intakeThread=...` (`apps/web/src/routes.ts` 31–34). |
| `POST /email-threads/.../create-draft-load` (API) | Backend creates a **draft** `Load` without stops (`app/services/email_threads.py` 223–237) — then user opens `LoadWorkspacePage` for that id. | Influences a load by **creating** a row; **stops** are not added there. |
| `POST /email-threads/.../link-load` (API) | Links an existing load to a thread — opens workspace with that load. | |

**Related:** `apps/web/src/routes.ts` `OPS.LOAD_NEW`, `OPS.LOAD_DETAIL`, `LOAD_INTAKE_THREAD_QUERY`, `LOAD_DISPATCH_ASSIGN_QUERY`.

---

## 2. Backend endpoint map (loads + parse + email + load lab)

| Method | Path | Router file | Handler | Service | Writes operational load data? | Returns `parse_response` / legacy `LoadDocumentParseResponse`? |
|--------|------|-------------|---------|---------|--------------------------------|------------------------------------------------------------------|
| POST | `/api/v1/loads` | `app/routers/loads.py` | `create_load` 26–38 | `loads_service.create_load` 143–205 | **Yes** — creates `Load` + optional `LoadStop` rows | N/A (response is `LoadResponse`) |
| GET | `/api/v1/loads` | `loads.py` 41–68 | `list_loads` | `loads_service.list_loads` | No | N/A |
| POST | `/api/v1/loads/parse-document` | `loads.py` 74–99 | `parse_load_workspace_document` | `load_document_parse.parse_load_workspace_from_pdf_bytes` | **No** (hydration only) | **Legacy** `LoadDocumentParseResponse` (`LoadDocumentParseResponse.model_validate`) |
| GET | `/api/v1/loads/{load_id}` | `loads.py` 102–112 | `get_load_detail` | `loads_service.get_load` | No | N/A |
| PATCH | `/api/v1/loads/{load_id}` | `loads.py` 115–133 | `update_load` | `loads_service.update_load` 291+ | **Yes** — CAS update; full replace `stops` if `stops` set on payload (413–423) | N/A |
| POST | `/api/v1/loads/{load_id}/confirm-document-snapshot` | `loads.py` 136–152 | `confirm_document_snapshot` | `confirm_load_customs_document_snapshot` | Yes (customs snapshot path) | N/A |
| POST | `/api/v1/loads/{load_id}/mark-ready` | `loads.py` 155–167 | `mark_load_ready` | `mark_load_ready` | Yes | N/A |
| GET/POST | `/api/v1/loads/{load_id}/notes` | `loads.py` 170–199 | `list_load_notes` / `add_load_note` | notes helpers | Optional write on POST | N/A |
| DELETE | `/api/v1/loads/{load_id}` | `loads.py` 202–213 | `delete_load` | `delete_load` | Yes | N/A |
| POST | `/api/v1/email-threads/{id}/create-draft-load` | `app/routers/email_threads.py` 154–167 | `create_draft_load_from_email_thread` | `email_threads_service.create_draft_load_from_review_thread` 133+ | **Yes** — creates `Load` (no stops in that function’s body) | N/A |
| POST | `/api/v1/load-lab/runs/upload` | `app/routers/load_lab.py` 64+ | (upload) | `load_lab` / extraction services | **No** to operational loads (persists `LoadLabExtractionRun` only) | Run row includes `parse_response` JSON when available (`load_lab` schemas) |
| POST | `/api/v1/load-lab/runs/{id}/semantic-extract` | `load_lab.py` 128+ | — | semantic / lab pipeline | **No** to operational loads | Updates run; `parse_response` may be set |

**Request/response shapes (summary):**

- **Create/Update body:** Pydantic `LoadCreate` / `LoadUpdate` in `app/schemas/load.py` — includes optional `stops: Sequence[LoadStopCreate]`.
- **Load response:** `LoadResponse` in same module — includes `stops: Optional[list[LoadStopOut]]` (see 241+ region).
- **Parse document response:** `LoadDocumentParseResponse` in `app/schemas/load_document_parse.py` — `document`, `extracted` (`LoadParseExtractedFields`), `raw_text`, `warnings`, `field_confidence`, `context`.
- **Frontend wrapper types:** `LoadWritePayload`, `LoadDocumentParseResponse` in `apps/web/src/api.ts` (826–875, 3303–3304, 3306+).

---

## 3. Exact JSON / type contract map

| Name | Where defined | Purpose |
|------|----------------|--------|
| `LoadDocumentParseResponse` | `app/schemas/load_document_parse.py` 66–72; **TS** `api.ts` 868–875 | **Workspace PDF** parse API response. |
| `extracted` (nested) | Pydantic `LoadParseExtractedFields` 43–64; **TS** `LoadDocumentParseExtracted` 844–866 | Normalized fields + `references` + `stops` for hydration. |
| `LoadDocumentParseStop` / `LoadParseStopItem` | `LoadParseStopItem` 23–40; **TS** `LoadDocumentParseStop` 828–842 | One parsed stop (pickup/delivery/drop + address/appt). |
| Load Lab `parse_response` | JSONB on `LoadLabExtractionRun` (`app/models/load_lab.py` 50); validated as `LoadDocumentParseResponse`-shaped in lab code (`app/services/load_lab_semantic.py`, `load_lab_review.py`) | **Lab-only** storage of last validated candidate; not returned by `POST /loads/parse-document`. |
| Semantic / model output | `app/schemas/load_lab_semantic.py` `LoadLabSemanticModelOutput` | Intermediate OpenAI-structured output before coercion to `LoadDocumentParseResponse`. |
| `critical_v1_1` output | `docs/critical_extraction_output.v1.1.json`, `app/schemas/critical_extraction_v11.py`, mapper `app/services/critical_extraction_v11_map.py` | **Canonical** broker/rate/stop **review** model; maps to `LoadParseExtractedFields` for promotion paths — **not** the browser `parse-document` default. |
| **Frontend hydration** (today) | `onParseWorkspacePdf` reads `res.extracted`, `res.raw_text`, `res.warnings` (`LoadWorkspacePage.tsx` 640–737) | Mutates React state; sets `internalNotes` from `raw_text` + optional customs line. |
| **Save payload** | `buildLoadPersistPayload` → `LoadWritePayload` with `stops: LoadStopWrite[]` (`loadWorkspaceShared.ts` 369–436; `api.ts` 3284–3304) | **Operational** create/update: full load scalars + ordered stop writes. |

**Important:** `LoadDocumentParseExtracted` in `api.ts` types `references` and `stops` as **required** arrays (864–865); the backend Pydantic models default them to `[]` if missing — keep alignment when cleaning types.

---

## 4. Cleanup candidate table (initial pass)

| File / function / area | Current purpose | Duplicate / temp / stale? | Keep / remove / refactor | Risk | Suggested order |
|--------------------------|----------------|----------------------------|----------------------------|------|----------------|
| `LoadWorkspacePage.tsx` `onParseWorkspacePdf` + local `extractedStopsToDraft` | Full PDF → state mapping | **Duplicate** of intent with docs referring to a non-existent `applyLoadDocumentParseResponse` module | **Refactor** — extract to one module to match tests/docs | Medium — regression in hydration | 1 (after contract tests) |
| `loadParseStops.ts` `filterMeaningfulParsedStops` | Drop parser shells | May be **too weak** for UX (“meaningful” ≠ useful address) | **Refactor** stricter or tiered filter | Low–medium | 2 |
| `loadWorkspaceShared.ts` `buildLoadPersistPayload` + `stopToPayload` | Persist all draft rows | **No** “omit empty” policy | **Refactor** optional server+client coalesce | Medium | 2–3 |
| `app/services/loads.py` `create_load` / `update_load` | Persist N stops as sent | **No** empty-row filter | **Refactor** optional defensive filter + audit | Medium (data semantics) | 3 |
| `app/services/load_document_parse.py` `_parse_stops` | Heuristic R/C stops | Can emit **many** blocks | **Refactor** cap + better block detection | High (parser) | 4 |
| `app/services/critical_extraction_v11_map.py` | critical → extracted | Parallel contract to heuristics | **Keep**; clarify docs vs `parse-document` | Low | doc-only anytime |
| `app/routers/load_lab.py` + `load_lab_semantic.py` | Lab experiments | **Not** in web nav | **Keep** isolated; do not conflate with workspace | Low | 5 |
| `email_threads` draft create | Create load without stops | — | **Keep**; **document** that stops come only from user/PDF/update | Low | doc |

---

## 5. Proposed cleanup order (slices, no code here)

1. **Lock behavior with tests (frontend)**  
   - **Prove:** `filterMeaningfulParsedStops` with fixtures from `load_document_parse` / recorded PDFs.  
   - **Proof command:** `cd apps/web && npm test -- loadParseStops` (extend tests).  
   - **Rollback risk:** Low (test-only).

2. **Clarify + optionally extract** `onParseWorkspacePdf`  
   - **Prove:** same JSON fixture → same React state before/after extract.  
   - **Proof:** Jest/RTL or pure unit on extracted function.  
   - **Rollback risk:** Low if behavior unchanged.

3. **Decide “empty stop” policy** (product): drop rows where `{facility, street, city, state, postal}` all empty; optionally keep appointment-only rows.  
   - **Client:** `buildLoadPersistPayload` or a dedicated `draftStopsForSave`.  
   - **Server:** optional second guard in `create_load` / `update_load`.  
   - **Proof:** API integration test with 11 null-heavy stops; expect fewer persisted or 400.  
   - **Rollback risk:** **Medium** — can change customer data shape; feature-flag or version if needed.

4. **Parser hardening** `_parse_stops`  
   - Cap max stops, improve block boundaries, reduce duplicate pickup/delivery from noise.  
   - **Proof:** PDF regression suite in backend tests.  
   - **Rollback risk:** High for extraction quality — deploy with monitoring.

5. **Docs / Lab**  
   - Align `docs/LOAD_LAB_*` with actual file layout (no phantom `applyLoadDocumentParseResponse.ts`).  
   - **Rollback risk:** None.

---

## 6. Acceptance tests (manual QA + automated ideas)

1. **Manual create, no PDF**  
   - Open `/loads/new`, enter minimal required broker/custom fields, **do not** upload PDF, save.  
   - **Expected:** Stops in DB = **2** (pickup + delivery defaults) with null address fields, **or** (if product changes) **0** after policy change — but **not** 11.  
   - **Check:** `GET /api/v1/loads/{id}` → `stops` length and row content.

2. **Manual create after noisy PDF (regression for “11 empties”)**  
   - Use a PDF that previously produced many spurious lines.  
   - **Expected:** Either fewer stops after filter/parser fixes, or explicit UI warning.  
   - **Proof:** capture `POST /api/v1/loads/parse-document` response JSON and compare `extracted.stops` length to persisted `stops` after create.

3. **Field coverage**  
   - If product requires hazmat / pallet from PDF, add explicit test once those fields exist on `LoadParseExtractedFields` and are mapped in `onParseWorkspacePdf`.

4. **Intake thread**  
   - From `/intake`, open linked load with `?intakeThread=`.  
   - **Expected:** Stops from server `hydrateFromLoad` only; no ghost stops from a previous `/loads/new` session (separate navigation).

5. **Concurrency**  
   - Edit load in two tabs; second save should 409 with version conflict — **existing** path; not specific to stops but worth smoke-testing after stop-filter changes.

---

## Quick reference: key line numbers (verify in editor)

| Concern | Location |
|---------|-----------|
| `isManual` | `LoadWorkspacePage.tsx` ~311–318 |
| Initial `draftStops` | `LoadWorkspacePage.tsx` ~375–377; `initialManualCreateStops` `loadWorkspaceShared.ts` 251–254 |
| `hydrateFromLoad` / `setDraftStops` | `LoadWorkspacePage.tsx` ~462–514 |
| Data-loading `useEffect` (manual vs id) | `LoadWorkspacePage.tsx` ~755–818 |
| PDF parse & stop replace | `LoadWorkspacePage.tsx` ~722–725, 261–291 |
| Persist payload + stops | `loadWorkspaceShared.ts` `buildLoadPersistPayload` 369–436; `stopToPayload` 200–216 |
| `create` / `onCreate` | `LoadWorkspacePage.tsx` ~895–936 |
| Backend persist stops | `app/services/loads.py` 176–181, 413–423 |
| Heuristic `stops` list | `app/services/load_document_parse.py` `_parse_stops` 286–392 |

---

*Last expanded: 2026-04-26 — documentation only; no code, commit, or push in the session that produced this file.*
