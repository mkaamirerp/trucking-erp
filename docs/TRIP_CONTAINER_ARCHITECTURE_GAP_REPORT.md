# Trip Container Architecture Gap Report

**As-of:** codebase inspection of `main` (models, `alembic_tenant` migration `e7f8a9b0c1d2_dispatch_trips_tenant_numbering`, core services, primary web entry points) plus the five product/architecture reference documents listed in the work request.  
**Out of scope for this file:** implementation, migrations, UI builds, Load Lab, parser, PDF (per request).

---

## 1. Executive summary

- **Current code is still load-centric:** The dispatch board (`GET /api/v1/dispatch/board`) returns **loads** grouped by `loads.status`, not trips. The canonical operational editing surface in the web app is still **`LoadWorkspacePage`** (routes `/loads/new`, `/loads/:id`). Intake, fleet, and payroll all anchor on that page.
- **`dispatch_trips` is a trip-number + linkage helper, not a full Trip container:** The table **owns** `trip_number` (with `tenant_dispatch_numbering` allocation) and enforces **exactly one** of `load_id` or `trailer_move_id` per row. It does **not** carry driver/truck/trailer; those remain on **`loads`**. There is at most **one active** `dispatch_trips` row per freight load (partial unique on active + `load_id`). That matches the locked **v1** rule in `DISPATCH_TRIP_NUMBER_RULE.md` (canonical `dispatch_trips`) but **conflicts** with the **target** in `TRIP_FIRST_DDL_CONTRACT.md`, which names an authoritative **`trips`** table with driver/truck/trailer and a separate **`trip_loads`** membership — i.e. **one real-world movement, many commercial loads** is not represented yet.
- **Locked product target (from foundation docs):** **TripWorkspacePage** (future) as the **final operational root**; data model with **`trips` + `trip_loads` +** unchanged contractual **`load_stops`**, with **trip_events / trip_stops / load_custody_events** as later, compatible layers for terminal/routing/custody.
- **LoadWorkspacePage must be retained** but **repositioned** over time: it stays the right place for **broker deal / commercial edit / contractual stops / documents / financial identity** and for **intake and verification**, not as the **sole** dispatch execution console.
- **Gap:** A large body of business logic, UI, and status semantics still treats **one load = one row on the board = one place to assign driver/truck** until **dispatched** mints a trip number. Moving **operational authority** to **Trip** while preserving **Load** as commercial truth requires **schema, service, and UI** work not present in the repo today beyond the `dispatch_trips` / read-model pattern.

---

## 2. Locked product decisions (from reference docs)

The following are treated as **locked** or **strongly specified** in `TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`, `TRIP_FIRST_DDL_CONTRACT.md`, `TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`, `DISPATCH_TRIP_NUMBER_RULE.md`, and `TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md` (narrative sections):

| Theme | Rule |
|--------|------|
| **Trip vs Load roles** | **Trip** = operational execution container (what runs on the road). **Load** = commercial / broker / contract record (what was booked and billed). |
| **Ownership** | **Trip** owns **trip number**, **operational** driver/team/truck/trailer (in target DDL), **operational** status/lifecycle, execution-oriented context. **Load** owns broker, rate, docs, refs, **contractual** stops, load-level money identity. |
| **Cardinality** | A **Trip** may contain **many** Loads. Membership must be **explicit** (target: **`trip_loads`**). |
| **UI direction** | **TripWorkspacePage** = future primary operational home; **LoadWorkspacePage** remains but is **not** the final dispatch root forever; **one** load form for commercial truth (no second “real” load form for production loads). |
| **Dispatch board** | Eventually **pivots** from **load** columns to **trip**-oriented work (per foundation narrative); not required to be true in current code. |
| **Stops** | **Contractual** load stops stay on **`load_stops`**; **operational** trip sequence / terminal legs are **separate** in the long run (`trip_stops` etc., future-compatible). |
| **Terminal / custody** | **Terminal routing, yard handoff, custody** are **future-compatible** requirements — not implemented as first-class trip/custody tables in current tenant schema beyond notes in the lifecycle doc. |
| **Doc tension to resolve in implementation** | `DISPATCH_TRIP_NUMBER_RULE.md` locks **`dispatch_trips`** as the **owner** of `trip_number` today. `TRIP_FIRST_DDL_CONTRACT.md` specifies a **`trips`** table with richer operational columns. Implementation must **reconcile** these (rename vs new table — see §7). |

---

## 3. Current backend schema state

| Area | Current behavior (verified) | Load-centric / trip-centric | vs target | Transitional reuse? |
|------|----------------------------|------------------------------|-----------|---------------------|
| **`app/models/load.py` — `Load`** | Full commercial + **operational** fields: `driver_id`, `truck_id`, `trailer_id`, `status` (incl. dispatch pipeline), `active_dispatch_trip_id`, `trip_number` (denorm). **`load_stops`**, notes, money fields. | **Load-centric**; trip fields are read-model or assignment mirror. | Target DDL says **load** should **stop** being authoritative for trip number and **operational** resource assignment. | **Yes:** keep as commercial + migration snapshots; service layer must shift authority to `trips`/`trip_loads` over time. |
| **`app/models/dispatch_trip.py` — `DispatchTrip`** | `trip_number`, `job_type`, `status` (active/cancelled), `load_id` **xor** `trailer_move_id`, timestamps. **No** driver/truck/trailer columns. | **Trip id + number** partial model; still **1:1** active row per load (freight). | **Conflicts** with multi-load trip; **aligns** with current trip-number law but **not** with full `trips` DDL (no ops assignment on row). | **Yes** as **allocator + audit** row; may **evolve** or **migrate** into `trips` (§7). |
| **`app/models/dispatch_trip.py` — `TenantDispatchNumbering`** | Per-tenant prefix, lock, `next_numeric`. | N/A (pool). | Same pool idea as `DISPATCH_TRIP_NUMBER_RULE.md`. | **Yes:** keep; allocation transaction stays in DB. |
| **`app/services/dispatch_trips.py`** | `ensure_active_trip_for_freight_load` mints `DispatchTrip` + `trip_number` in same txn as sequence bump; `cancel_active_trip_for_load` for certain status regressions; `_sync_load_read_model` concept used when cancelling. | **Load-scoped** entrypoints (`load_id`). | **Conflicts** with “trip owns many loads” until membership + trip-level APIs exist. | **Yes:** core allocator to extend or wrap. |
| **`app/services/loads.py`** | `update_cas` path: on transition **into** `TRIP_ALLOCATED_AT_LOAD_STATUS` (`dispatched`), requires driver+truck, calls `ensure_active_trip_for_freight_load`, sets `active_dispatch_trip_id` + `trip_number` on load; cancels active trip when moving to pre-dispatch statuses in `PRE_DISPATCH_TRIP_CANCEL_STATUSES`. `list_loads_for_board` groups **loads** by `Load.status`. | **Strongly load-centric** dispatch truth. | **Conflicts** with trip-first authority until **trip** drives assignment and **load** is attached. | **Yes** during transition with dual-write/snapshot rules. |
| **Alembic tenant `e7f8a9b0c1d2_...`** | Creates `dispatch_trips`, `tenant_dispatch_numbering`, `loads.active_dispatch_trip_id` + `loads.trip_number` + FK to `dispatch_trips`. | Implements v1 trip-number product. | **No** `trip_loads` or `trips` as in DDL contract. | **Foundational**; new tables add beside or replace (§7). |
| **`app/schemas/load.py` — `LoadResponse` / statuses** | `DISPATCH_STATUSES` / `ALLOWED_STATUSES` for loads; used everywhere loads surface. | Load lifecycle as **the** board axis. | Board eventually **trip**-keyed; load statuses may remain **commercial** or split (product). | **Yes** for APIs until trip DTOs exist. |
| **`app/routers/loads.py`** | CRUD + parse-document + CAS update paths for load body. | **All** primary writes go through **load** resource. | Need **trips** + **trip_loads** routers or nested routes. | **Yes**; add parallel resources. |
| **Dispatch board** | `app/routers/dispatch.py` `GET /dispatch/board` → `loads_service.list_loads_for_board`. | **Purely load-centric.** | **Conflicts** with trip board target. | **Yes**; keep until trip grouping ships. |

---

## 4. Current frontend / workspace state

| Surface | Role today | Assignment / dispatch | Driver / truck / trailer | Trip number | What must move later |
|---------|------------|------------------------|---------------------------|-------------|----------------------|
| **`LoadWorkspacePage`** | **Primary** create/edit for loads (manual, detail, intake, payroll view). Persists via `buildLoadPersistPayload` → API. | **Yes** — status transitions, resources; **first entry to `dispatched`** triggers backend trip mint (see §5). | Edited in workspace form (assignment section). | Shown when `load.trip_number` / active trip (e.g. header + context row). | **Operational “final commit”** and **board-equivalent** actions move toward **TripWorkspacePage**; load page keeps **commercial** edit. |
| **`LoadWorkspaceForm`** | One canonical form for load fields + sections. | Through load save / patch. | Same. | Display-only trip context where provided on load DTO. | **Operational** fields **eventually** read/write via **trip** context or snapshots only. |
| **`DispatchPage`** | **`getDispatchBoard`** — loads grouped by **`load.status`** in columns; unassigned **Assign** → navigates to `/loads/{id}?dispatchAssign=1`. | **Board is load cards**, not trip rows. | Shown on cards; assignment flow lands on **load** workspace. | Shown on card when present on `Load`. | **Pivot** to **trip**-keyed board + **open Trip** instead of (or in addition to) **Load**. |
| **`LoadsListPage`** | List + navigate to `LOAD_DETAIL` / `LOAD_NEW`. | Indirect. | N/A. | N/A. | Add **trips** list / deep links when **Trip** exists. |
| **`LoadInboxPage`** | Intake: create **draft** load, open `LoadWorkspacePage` with intake thread. | Indirect. | On workspace after open. | As on load. | Intake may later **attach** drafts to a **trip**; still use **load** form for commercial body. |
| **`routes.ts` / `App.tsx`** | `OPS.LOAD_NEW`, `LOAD_DETAIL`, etc.; no `TripWorkspace` routes. | N/A | N/A | N/A | New **`/trips/...`** routes when built. |

**Current “owner” of dispatch actions:** In practice, **status and resources** on **`PATCH /api/v1/loads/{id}`** with CAS; **UI** is **`LoadWorkspacePage`** and **`DispatchAssignmentStrip`** (unassigned + `?dispatchAssign=1`). There is **no** trip-scoped API or page.

---

## 5. Current trip-number implementation vs future Trip table

**Today (code + `DISPATCH_TRIP_NUMBER_RULE.md`):**

- **`dispatch_trips`** is the **canonical** row for **`trip_number`**; **`TenantDispatchNumbering`** allocates the string in the same transaction as the insert.
- **Exactly one** target per row: `load_id` or `trailer_move_id` (trailer move reserved for future).
- **Minting:** In `loads.update_cas`, when status becomes **`dispatched`** (and was not before), the service requires **driver + truck**, then calls `ensure_active_trip_for_freight_load`, then writes `active_dispatch_trip_id` and **`trip_number` on the load** (read-model + convenience).
- **Cancellation:** Active trip is cancelled and read-model cleared only when moving to certain **pre-dispatch** statuses (`draft`, `ready`, `unassigned`), not when entering e.g. `in_transit` (per `PRE_DISPATCH_TRIP_CANCEL_STATUSES`).
- **`Load`** still stores **authoritative** `driver_id` / `truck_id` / `trailer_id` for the product today — the **`DispatchTrip`** row does **not** duplicate equipment.

**Future (`TRIP_FIRST_DDL_CONTRACT.md` — `trips`):**

- **Broad operational container:** `status` (rich enum: draft → cancelled), `completion_policy`, `dispatch_mode`, **driver / secondary driver / truck / trailer**, optional terminal FKs, timestamps, notes — i.e. **operational** truth on **`trips`**, not on **`loads`**.

**Gap:** Two different “trip” concepts — **(a)** current **`dispatch_trips`** = number + 1:1 load link, **(b)** target **`trips`** = full ops container + **`trip_loads`**. The doc set must be merged in implementation.

**Options to reconcile (high level — see §7):**

| Approach | Pros | Cons |
|----------|------|------|
| **Evolve `dispatch_trips` → add columns** (equipment, trip lifecycle enums, nullable `load_id` for multi-load?) | Reuses `trip_number` + indexes; one table name in compliance checklist. | Current **CHECK** and **1:1 load** indexes **fight** multi-load; likely **breaking** migration. |
| **New `trips` + `trip_loads`, migrate `dispatch_trips` data** | Clean separation; matches DDL contract. | Data migration, dual-read period, **re-home** `trip_number` ownership carefully. |
| **Keep `dispatch_trips` legacy, add `trips` parallel** | Low blast radius to old code paths. | **Two** number/allocation stories unless strictly phased out — **risk** of drift. |

**Recommendation (for §7/§10):** Favor a **designed** path (A or B) with explicit **cutover** of **`trip_number` authority** and **load** read-model fields — do **not** let two trip concepts linger without a sunset plan (C is highest drift risk).

---

## 6. Required schema target (from docs — not migrations)

**Authoritative (V1 target from `TRIP_FIRST_DDL_CONTRACT.md`):**

1. **`trips`** — Operational container: `trip_number` **unique (tenant)**, `status` + `completion_policy` + `dispatch_mode`, assignment FKs to driver/truck/trailer (per tenant’s driver/truck model), optional `origin_terminal_id` / `target_terminal_id`, timing, notes, audit columns.
2. **`trip_loads`** — `trip_id`, `load_id`, `status_within_trip`, `sequence_hint` optional, `added_at` / `removed_at`, audit; **unique active membership** (e.g. partial unique when `removed_at` null).
3. **`loads` — transitional:** Snapshot / legacy columns allowed (`trip_number` snapshot, `active_trip_id`-style FK) with **non-authoritative** semantics for ops fields once **`trips`** is live; **commercial** fields unchanged in purpose.
4. **`load_stops`** — **Unchanged** as **contractual** stop plan (per contract + integration map); authority remains load-scoped.
5. **Future (after V1):** **`trip_events`**, **`trip_stops`**, **`load_custody_events`** — operational sequence, terminal/routing, custody/handoff; compatible with `TRIP_LIFECYCLE_...` note.

**Explicit non-goals in this section:** no Alembic, no ORM, no API shapes — **target only**.

---

## 7. Migration strategy options (comparison)

| Criterion | **Option A — Rename / evolve `dispatch_trips` into `trips`** | **Option B — New `trips` + `trip_loads`, migrate off `dispatch_trips`** | **Option C — Keep `dispatch_trips`, add separate `trips`** |
|----------|----------------------------------|----------------------------------------|----------------------------------|
| **Pros** | One physical table for trip number in compliance docs; fewer names in ops headspace. | Clean multi-load model; matches DDL; can migrate **rows** to `trips` + `trip_loads` with a script. | Phased delivery possible without rewriting allocator immediately. |
| **Cons** | **Hard** while **1:1 load** constraints and CHECKs exist; multi-load **requires** dropping/replacing constraints. | Two-step migration, dual-write or freeze window, full regression. | **Highest** risk of two allocators, two mental models, bugs in read-model. |
| **Risk** | Medium–high schema surgery on hot path. | Medium operational risk; well-controlled if feature-flagged. | **High** long-term consistency risk. |
| **Trip number allocation** | Still one pool if table renamed and allocator updated in place. | Point allocator at **`trips`**; **retire** `dispatch_trips` after migration. | Must ensure **one** pool — easy to get wrong. |
| **`loads.active_dispatch_trip_id` / `trip_number`** | Evolve FK target or rename; update CAS sync. | Replace with `active_trip_id` (DDL suggests) and snapshot columns; backfill. | Risk of which FK is “active”. |
| **Tests & UI** | All trip-number and board tests need updating together. | Parallel tests for new tables; shims for UI. | Duplicated test matrices. |
| **Recommendation** | Viable if team commits to **one** big migration and **naming** alignment with `TRIP_FIRST_DDL_CONTRACT.md`. | **Best fit** to foundation docs if you accept explicit migration. | **Not recommended** unless as **very** short bridge with documented sunset. |

---

## 8. Implementation phases (suggested)

| Phase | Intent | Likely files / areas | Tests | Must not break |
|-------|--------|------------------------|-------|----------------|
| **0 — Protect current behavior** | Lock regression budget; document authority boundaries. | CI, `tests/test_dispatch_trip_numbers.py` (and related), monitoring | Integration tests for `dispatched` + trip mint + cancel rules | **Existing** `PATCH` load, board, trip prefix admin |
| **1 — Schema foundation** | Introduce **`trips`**, **`trip_loads`** (and snapshots on `loads` per contract). | `alembic_tenant/`, `app/models/`, new services | **Migration** dry-run, tenant preflight | **No** change to public API behavior without flags |
| **2 — Service authority shift** | Trip service **owns** ops assignment; load patch **stops** being sole writer of driver/truck for dispatched work (staged). | `app/services/dispatch_trips.py` or new `trips.py`, `loads.py` | Service + CAS tests, concurrency | **Manual load create**, **intake** |
| **3 — TripWorkspacePage shell** | Read-only or minimal create trip; **no** full board pivot yet. | `apps/web/src/pages/`, `App.tsx`, `routes.ts`, `api.ts` | E2E/smoke, routing | **LoadWorkspace** flows |
| **4 — Add load to trip** | `trip_loads` insert; deep-link to load create with `tripId` query (pattern in integration map). | Routers, services, web | API tests membership rules | **Save load** path, **stops** |
| **5 — Move assignment / trip status out of LoadWorkspacePage** | Operational strip moves to **Trip**; load shows **snapshots** / links. | `LoadWorkspacePage`, `LoadWorkspaceForm`, new trip components | UI + API tests | **Commercial** load edit, **parse-document** (unchanged) |
| **6 — Dispatch board → trips** | `list_*_for_board` for trips; load board deprecated or secondary. | `DispatchPage`, `dispatch.py` router, services | Board sorting, unassigned | **Trip number** search continuity |
| **7 — Terminal / custody** | `trip_stops`, `load_custody_events`, handoff rules. | New models/services | Domain tests | **Earlier** phases stable |

**Parser / PDF / Load Lab:** **No** work in any phase per this report’s charter; do not block Trip work on them.

---

## 9. Backward compatibility (transition)

- **Manual load create:** Stays `POST /loads` + `LoadWorkspacePage`; no trip **required** until product attaches trip (Phase 4+).
- **Intake draft load:** Unchanged; later optional **“add to trip”** is additive.
- **PDF-assisted prep:** Stays **hydration-only** to load; must **not** create `trips`/`dispatch_trips` (already aligned in integration map).
- **Existing dispatch board:** Can keep **load**-based `GET /dispatch/board` until Phase 6; mobile/alternate clients depending on it need **versioning** or parallel endpoint.
- **Current trip numbers:** Rows in **`dispatch_trips`** + denorm on **`loads`** remain valid history; migration must **preserve** `trip_number` strings and **never reuse** (per locked rule).
- **Loads with `active_dispatch_trip_id`:** Migration maps each to **`trips.id`** (or temporary bridge row) and **`trip_loads`**; OR keeps FK compatible if renaming tables.

---

## 10. Open decisions for product owner

1. **Evolve `dispatch_trips` into `trips` vs new `trips` table vs short-lived parallel** — see §7; foundation DDL favors a dedicated **`trips`** shape; `DISPATCH_TRIP_NUMBER_RULE.md` is **`dispatch_trips`**-worded. Pick one **ownership** story for **`trip_number`**.
2. **Empty trip allowed?** (Draft/planned **trip** with **zero** loads) — **allowed or forbidden** for v1 trip workspace.
3. **When to mint trip number in the new model** — Still only on first **“dispatched”**-equivalent operational commit, or earlier (e.g. “planned” trip)?
4. **LoadWorkspace “final” action** — On **Save**, does the business **ever** create a **trip** row immediately, or only when attaching to a trip or hitting a **“dispatch”** action on the **Trip** side?
5. **UX: add load to trip** — Full page vs drawer vs modal (foundation doc and integration map list both).
6. **Active membership** — **One** load in **at most one** active trip at a time; **sequential** re-use across trips (history) vs stricter — affects **`trip_loads` uniqueness** and APIs.

---

*End of gap report. No code, migration, or UI implementation is implied or authorized by this document alone.*
