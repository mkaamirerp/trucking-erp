# Trip Container + Load Page + Parser Integration Map

**Status:** Product / architecture map — **not** a committed implementation plan. **As-of:** repo `main` with Load workspace stop-safety and documented Load Lab / web drift.  
**Do not** treat this file as a spec for immediate coding without a separate cutover decision.

---

## 1. Product direction summary

**Anchor rule:** `LoadWorkspaceForm` is the product form. Load Lab may test, preview, and debug extraction, but it must never become a second production load form.

| Concept | Role |
|--------|------|
| **Trip (dispatch trip)** | **Operational** container for what runs on the road: a **trip number**, lifecycle, and (today) **assignment context** that dispatch owns. The physical move is the unit of dispatch. |
| **Load** | **Commercial** record: broker, rate confirmation, **stops**, **references**, linehaul economics, and documents that look like a **broker deal**. A load is what you book and get paid on. |
| **Load page / `LoadWorkspaceForm`** | The **one canonical** surface for **creating and editing** a load in the app — **manual**, **detail**, or **intake** modes. This is the final form model: no second “real” load form should exist. |
| **Load Lab + parser pipeline** | **Extraction engine** and **test/debug surface** — proves prompts, heuristics, `parse_response` shape, and regression on PDFs. It must **not** become the production load page. Proven code paths should **feed** the real page’s **PDF assist** (hydration only), not replace the form. |
| **PDFs** | **Optional assist** for many loads; **not** all loads have PDFs. **City/local, dispatch-created, and manual** loads must work **without** any file. Intake/email can **suggest** data but should **hydrate the same** `LoadWorkspaceForm` when operators accept or review. |
| **Future “Trip container” (product target)** | **One trip can reference many loads** in the long-term product story; **Trip-owned** context (which driver/truck/trailer is rolling) belongs on the **trip** side of the boundary, while **broker/RC/stop** details stay on **load** rows. **Today’s schema** (see §6) is **load-centric dispatch trip** (one `dispatch_trips` row per active freight load), not a multi-load trip membership table — the target is **forward-looking**. |

---

## 2. Current real Load page entry points (code-verified)

All production load editing uses **`LoadWorkspaceForm`** from **`LoadWorkspacePage`** (`apps/web/src/pages/LoadWorkspacePage.tsx`), except as noted.

| How users arrive | File(s) | Route / navigation | Component | Create / edit / view | PDF | Trip context in UI today |
|------------------|----------|--------------------|-----------|------------------------|-----|---------------------------|
| **New load (manual)** | `App.tsx` ~214; `LoadWorkspacePage.tsx` ~311–333 | ` /loads/new` | `LoadWorkspacePage` | **Create** (POST after fill) | Optional — hidden PDF + `onParseWorkspacePdf` calls `parseLoadWorkspaceDocument` (`~631+`) | **None** (no trip selector on page) |
| **Edit / view existing load** | `App.tsx` ~215; `LoadWorkspacePage` | ` /loads/:id` | `LoadWorkspacePage` | **Edit** (PATCH) + view notes, audit, settlement per mode | Yes — `canWorkspaceParsePdf` in manual, intake, detail (`~631–632`) | **Read-only** trip number on load when `active_dispatch_trip_id` is set (`LoadWorkspacePage` ~1276+); assignment strip for unassigned + `?dispatchAssign=1` |
| **Load list “+ New load”** | `LoadsListPage.tsx` ~111–116 | `navigate(OPS.LOAD_NEW)` → `/loads/new` | → `LoadWorkspacePage` | Create | As above | None |
| **Open load from list row** | `LoadsListPage.tsx` ~152 | `navigate(OPS.LOAD_DETAIL(load.id))` | `LoadWorkspacePage` | Edit | As above | As above |
| **Dispatch board** | `DispatchPage.tsx` ~620–726; comment ~3 | Unassigned: ` /loads/{id}?dispatchAssign=1` | `LoadWorkspacePage` + `DispatchAssignmentStrip` | **Edit** (assign resources) | PDF possible on same page | **Dispatch** — assignment strip; trip exists after status moves into dispatched path (backend) |
| **“New load” from dispatch empty column** | `DispatchPage.tsx` ~694, ~725–726 | `navigate(…OPS.LOAD_NEW)` | `LoadWorkspacePage` | Create | Optional | None |
| **Intake: create draft load from email** | `LoadInboxPage.tsx` ~479+; `api.ts` `createDraftLoadFromEmailThread` | API `POST /api/v1/email-threads/{id}/create-draft-load` then navigate `OPS.LOAD_WORKSPACE_INTAKE` → ` /loads/{id}?intakeThread=…` | `LoadWorkspacePage` in **intake** mode | **Creates** load row on server first, then **edits** in workspace | PDF assist via same `parseLoadWorkspaceDocument` on workspace + thread context; email **create draft** does **not** use full `load_document_parse` for the row body (see `CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`) | None in UI |
| **Intake: open linked load** | `LoadInboxPage.tsx` ~609+ | ` /loads/{id}?intakeThread=…` | `LoadWorkspacePage` intake | Edit | Optional | As detail |
| **Inbox: manual entry shortcut** | `LoadInboxPage.tsx` ~1013 | `navigate(OPS.LOAD_NEW)` | `LoadWorkspacePage` | Create | Optional | None |
| **Dashboard / other links** | `DashboardPage.tsx` ~133+ | Href ` /loads` | `LoadsListPage` | List only | N/A | N/A |
| **Fleet** | `FleetPage.tsx` ~250 | ` /loads/{id}` | `LoadWorkspacePage` | Edit | Optional | As detail |
| **Payroll settlement section** | `LoadWorkspaceForm` + `SectionSettlement` | Under ` /loads/:id?mode=payroll` (query) | `LoadWorkspacePage` | Mostly view payroll slice | N/A | Read trip number on load for display where applicable |

**Not in current `apps/web` production bundle:** a dedicated **Load Lab** page, `/loads/lab` route, or `api.ts` `load-lab` client helpers (see prior reconciliation). Lab remains **API/backend**-accessible.

---

## 3. Manual load flow (today)

| Stage | What happens |
|-------|----------------|
| **Entry** | User hits `/loads/new` (list, dispatch, or inbox) — `LoadWorkspacePage` with `isManual` true (`~317–318`, `~325–326`). |
| **Initial state** | `useState` initializers: e.g. `status` **unassigned**, empty strings for most fields, `draftStops` from `initialManualCreateStops()` → **2** default stops (PICKUP + DELIVERY) in `loadWorkspaceShared.ts` (see stop-safety commit `f66e4759` and `selectDraftStopsForPersist`). |
| **Required fields (product/UX)** | **No hard frontend gate** in this map — create goes to API with server validation (brokers, drivers, unique load number, etc. per `app/schemas/load.py` + `app/services/loads.py`). **Parser is not required.** |
| **Save payload** | `buildLoadPersistPayload` (`loadWorkspaceShared.ts`) → `POST /api/v1/loads` via `createLoad` (`api.ts` ~817). |
| **Backend** | `app/routers/loads.py` `create_load` → `loads_service.create_load` — creates **Load** + **stops** from payload. |
| **If no PDF** | Form stays entirely user-driven; `onParseWorkspacePdf` never run unless user picks a file. **Manual creation does not depend on parser.** |

**Must remain true for product:**

- **Manual creation** and **no-PDF** paths stay first-class (city/local, dispatch-empty-board, quick entry).
- **Parser** is **assistive** (hydration), never a gate for “can create a load.”
- **Intake** may create a **draft** load server-side, but **editing** still lands on the **same** `LoadWorkspaceForm` — alignment with “one form” is already the architecture for intake mode.

---

## 4. PDF-assisted load flow

### 4.1 Current (code-grounded)

| Layer | Today |
|-------|--------|
| **Endpoint** | `POST /api/v1/loads/parse-document` — `app/routers/loads.py` `parse_load_workspace_document` → `parse_load_workspace_from_pdf_bytes` (`app/services/load_document_parse.py`). **Does not** persist a load. |
| **Response shape** | Pydantic `LoadDocumentParseResponse` / TS `LoadDocumentParseResponse` in `api.ts` — `document`, `extracted`, `raw_text`, `warnings`, `field_confidence`, `context`. |
| **Client hydration** | `LoadWorkspacePage` `onParseWorkspacePdf` (`~634+`) — reads `res.extracted`, `raw_text`, `warnings`; updates React state; stops via `filterMeaningfulParsedStops` + `extractedStopsToDraft` (local to page in current tree). |
| **Load Lab (backend)** | `POST /api/v1/load-lab/runs/upload` and related routes persist **`load_lab_extraction_runs`**, including **`parse_response`**, normalized package, semantic/lab review metadata — **no** `loads` write from those routes. **No** matching production web client in `apps/web` today. |
| **Limitations** | Regex/easy heuristics in `load_document_parse.py`; stop inflation, weak global extraction; not unified with email intake TQL path — see `docs/CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`. Client-side **stop-safety** filters (commit `f66e4759`) reduce bad stops on save, not the raw parser. |

### 4.2 Target (product-aligned, not yet fully implemented)

1. **One proven pipeline** (Lab-hardened: normalized package, optional semantic/validation) called **from the server** in support of the **same** public contract: **`LoadDocumentParseResponse`**, or a **strict superset** with the same `extracted` + `raw_text` semantics for the workspace.  
2. **Shared helper** (e.g. `applyLoadDocumentParseToWorkspaceDraft` / shared stop + scalar map) so **one** code path updates draft state from `extracted` + options — `LoadWorkspacePage` and any future read-only lab preview use the same mapping.  
3. **Operator** always **reviews and saves** through **`buildLoadPersistPayload` → `POST/ PATCH /loads`**. **No** automatic operational write from parser or from Lab run rows.  
4. **Optionally** replace the **public** `parse-document` **implementation** with an **adapter** that reuses the same internal path as load-lab (same pins, same validation) while keeping the **route** stable for the Load page.

---

## 5. Load Lab role

- **Remains** a **testing / regression / admin-proving** surface: persisted runs, JSON/candidate review, `semantic-extract`, `lab-review`, field-learning, OpenAI smoke — **isolated** from **dispatch/payroll** truth.  
- **Is not** renamed or promoted to “the” production load experience. **One** canonical form: **`LoadWorkspaceForm`**.  
- If a **Lab UI** is restored later, it should **preview** the same form **read-only** (as in `docs/LOAD_LAB_WORKSPACE_PARITY_NOTE.md`) plus lab-only panels — **not** a second “final” schema.  
- **No** default **POST/PATCH** to **`/loads`** from Lab unless a **separate, explicit, audited “promote”** flow exists; **no** such route is in `app/routers/load_lab.py` at time of this document.

---

## 6. Trip container target flow (product vs current schema)

### 6.1 Product target (narrative)

- **Create trip** (operational: trip number, resource intent, status).  
- **Attach one or many loads** to that trip (commercial legs / broker deals).  
- **Manual** new load: same **`LoadWorkspaceForm`** whether started from “Loads” or “inside trip” — **no PDF required**.  
- **PDF-assisted** load: same form, hydrate from `LoadDocumentParseResponse` / `parse_response`-equivalent, then **user saves** load.  
- **Attach existing** load: pick by id/search; membership links **trip ↔ load** without re-copying load rows.  
- **Ownership model:** **Trip** holds **operational** dispatch context (in the long term: **primary** home for driver/truck/trailer when that is the product decision). **Load** holds **broker / RC / money / stop** / commercial truth. A **`trip_loads` (or similar) join** models **M:N** or ordered membership — **not** in production schema as of this map’s “today” (see below).

### 6.2 Current implementation (factual, `main`)

- `DispatchTrip` (`app/models/dispatch_trip.py`) has a **single** `load_id` (freight) **or** `trailer_move_id` — **v1: one load per active freight trip row**, with unique index `uq_dispatch_trips_tenant_load_active` for active loads.  
- `Load` has `active_dispatch_trip_id`, `trip_number` (denormalized for list/search), and relationship `dispatch_trips` — **read-model** and allocation wiring (`app/services/dispatch_trips.py`, `app/services/loads.py`).  
- So the **“one trip, many loads”** story is a **model evolution**; this document does **not** assert it is implemented.

---

## 7. Save / commit contract (safe sequence)

1. **Load form** is the only normal path to create/update **operational** load rows: `POST/ PATCH /api/v1/loads` with `LoadCreate` / `LoadUpdate` and stops.  
2. **Parser** and **Load Lab** produce **candidates** / **client draft only** (parse-document) or **non-operational** run rows (load-lab) — they **do not** replace step 1.  
3. **Trip–load attachment** (once multi-load trip exists) should **link** an already-saved **Load** to a **Trip** — e.g. insert membership row, not overwrite load commercial fields from parser.  
4. **Dispatch assignment** that allocates a **trip** uses existing services (`ensure_active_trip_for_freight_load`, etc.); **trip number** and **active trip id** on load are **updated by that flow**, not by PDF.  
5. **No** `parse_response` or Lab JSON should **write** **Trip** or **Load** in production without an explicit **user commit** to the right API (or a clearly scoped future **promote** with audit).  
6. **Parser must not** create **operational** trip data (no silent `dispatch_trips` rows from PDF alone).

---

## 8. Minimal implementation sequence (phased, safe)

| Phase | Content |
|-------|--------|
| **1** | **Stabilize** current `LoadWorkspacePage` + manual + PDF + stop safety (`f66e4759` and follow-ups as needed). Document / fix doc drift; **no** Load Lab as production page. |
| **2** | **Extract** shared **hydration** from `onParseWorkspacePdf` to a testable **helper** (single mapping from `LoadDocumentParseResponse` → partial draft patch). |
| **3** | **Adapter** on backend: `parse-document` may **delegate** to the same internal pipeline as Lab (or stricter) while keeping **response contract**; feature-flag if needed. |
| **4** | **Trip container shell** + **data model** for **many loads per trip** (e.g. `trip_loads`, migration, APIs) if product signs off; **do not** fork the load form. |
| **5** | **“Add load to trip”** flows: deep-link to same **`/loads/new?tripId=…`** or in-trip modal — **always** the same `LoadWorkspaceForm` save path, then **attach** membership. |
| **6** | **Optional** Lab UI restore: **read-only** `LoadWorkspaceForm` + JSON panels; still **no** default promote. |

**Implementation priority:** The next implementation step is not the full Trip schema/container yet unless the `LoadWorkspaceForm` and parser hydration path are stable. First extract a shared `LoadDocumentParseResponse` / `parse_response` hydration helper from `LoadWorkspacePage`, then wire the proven parser/Lab backend pipeline behind the real Load page PDF-assist flow, then resume Trip container evolution.

---

## 9. Things not to do

- **Do not** market or implement Load Lab as **the** production load page.  
- **Do not** add a second “final” load form.  
- **Do not** require PDF for any load.  
- **After** trip owns operational authority, **do not** make **load** the long-term **source of truth** for **driver/truck/trailer** if product says those belong to **Trip** (migrate carefully; `Load` may keep snapshots during transition).  
- **Do not** have the parser or Lab runs **create** or **mutate** **Trip** (or `dispatch_trips`) without an explicit, audited product action.  
- **Do not** remove or regress **manual** load creation.  

---

## 10. Open decisions (product only)

These need explicit product answers before implementation; **this doc does not decide them.**

1. **Add load inside trip — UX:** full-page (same as today), **modal**, or **side panel**?  
2. **PDF-assisted** draft: **auto-save** a `draft` load row on first parse, or **only** hydrate client state until user clicks **Save**? (Today: **client-only** until save on manual create; intake draft is different.)  
3. **Trip** allowed with **zero loads** for a while (e.g. planning) or must always have ≥1?  
4. **Same load** attachable to **multiple trips** over time (completed vs active membership), or **at most one** active trip membership? Historical replay vs strict uniqueness.  

---

*End of map — report-only artifact; no code, commit, or push implied by this file.*
