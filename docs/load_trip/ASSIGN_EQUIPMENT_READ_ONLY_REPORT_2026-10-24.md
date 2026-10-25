# Assign equipment read-only report (Task 19)

**Date:** 2026-10-24  
**Scope:** What exists today for assigning driver, truck, and trailer to a load/trip. No design proposals.  
**DB evidence:** Read-only `psql` against `tenant_demo` inside `truckerp-api` (2026-10-25 UTC).  
**Code authority:** Repository at `/home/admin/trucking_erp` on branch `gpt-review` at time of writing.

---

## Executive summary

Operational assignment today is **Trip-owned**: `trips.driver_id`, `trips.truck_id`, `trips.trailer_id` via `PUT /api/v1/trips/{id}/assignment`. Load create/PATCH **rejects** `driver_id` / `truck_id` / `trailer_id`. The load workspace shows driver/truck/trailer as **read-only mirrors**; dispatch home lists drivers and unassigned loads but **does not** assign or drag-drop. There is **no** service that returns “trailer from driver’s most recent **trip**”; hints use **legacy load rows** or **equipment `owner_person_id`**. `load_stop_actions` supports `drop_trailer` / `hook_trailer` in schema only—**no API/UI writers** found. Driver busy on a second open trip is **not** blocked (only schedule overlap against **in_progress** trips with bounds).

---

## 1. Driver table (and related person tables)

### 1.1 `drivers` (operational dispatch roster)

**ORM:** `app/models/driver.py`  
**DB (`tenant_demo`):** `\d drivers` matches ORM (no extra assignment columns).

| Column | Type (DB) | Nullable | Relevant to assignment? | Who writes | API / UI today |
|--------|-----------|----------|-------------------------|------------|----------------|
| `id` | integer | NOT NULL | PK | INSERT on create/approval | `POST /api/v1/drivers`, onboarding approval |
| `tenant_id` | integer | NOT NULL | isolation | same | all tenant routes |
| `person_id` | bigint | YES | links to `people` for ownership hints | onboarding / people sync | People-first projection rules |
| `payee_id` | integer | YES | payroll, not dispatch equipment | payroll flows | not assignment UI |
| `first_name`, `last_name` | varchar | NOT NULL | display | `POST/PATCH /drivers`, onboarding | driver lists, trip assignment dropdowns |
| `email`, `phone` | varchar | YES | contact | same | driver CRUD |
| `is_active` | boolean | NOT NULL | roster filter | PATCH | `listDrivers`, dispatch home (`include_inactive: false`) |
| `hire_date`, `termination_date` | date | YES | HR | PATCH | driver admin |
| `issuing_country`, `issuing_region`, `license_number`, `license_class`, `license_issue_date`, `license_expiry_date` | various | YES | compliance | PATCH; synced from `driver_profiles` per people workspace | license warnings on dispatch home |
| `created_at`, `updated_at` | timestamptz | NOT NULL | audit | DB | — |

**Not on `drivers`:** default truck, assigned truck, current trailer, long-haul vs city, pay type, home terminal.  
Evidence: full column list `app/models/driver.py` lines 19–48; DB `\d drivers` on `tenant_demo`.

### 1.2 `driver_person_extensions` (role config — operating pattern, not equipment FKs)

**ORM:** `app/models/driver_person_extension.py` lines 42–51.

| Column | Type | Nullable | Meaning | Writers | API / UI |
|--------|------|----------|---------|---------|----------|
| `employment_relationship_type` | varchar(50) | NOT NULL | `company_driver` \| `owner_operator` | People workspace PATCH | `PATCH /api/v1/people/{person_id}/driver-role-configuration` (`app/routers/people_workspace.py` 271–284) |
| `driver_operating_subtype` | varchar(50) | NOT NULL | `long_haul` \| `city_local` \| `shunt_yard` | same | same GET/PATCH (`people_workspace.py` 247–268, 271+) |
| `is_team_driver`, `team_role_type` | bool / varchar | | team driving | same | same |
| `provides_own_truck`, `provides_own_trailer` | bool | NOT NULL | equipment contribution flags | same | same |
| `equipment_contribution_type` | varchar(50) | NOT NULL | enum set in `app/schemas/driver_person_extension.py` 17–19 | same | same |
| `insurance_commercial_approved` | bool | NOT NULL | compliance | same | same |

Allowed subtype values: `DRIVER_OPERATING_SUBTYPES` at `app/schemas/driver_person_extension.py` lines 15–15, 43–51.

**Not stored here:** `default_truck_id`, `home_terminal_id` (documented as future-only in `docs/people_driver/DRIVER_ADMIN_CONFIG_PHASE1_FIELD_LOCK.md` — not in schema).

**DB (`tenant_demo`):** `SELECT COUNT(*) FROM driver_person_extensions` → **3** rows.

### 1.3 `driver_profiles` (license slice on person)

**ORM:** `app/models/person.py` lines 102–128 — `license_number`, `license_region`, `license_expiry`, `is_active` only.  
**PATCH:** `DriverProfilePatch` `app/schemas/people_workspace.py` 139–145; router `people_workspace.py` (driver profile path separate from role configuration).

### 1.4 `people` (address — not “home terminal”)

**ORM:** `app/models/person.py` lines 38–43 — `street_address`, `city`, `region`, `postal_code`, `country`. No `home_terminal_id` or terminal FK.

---

## 2. Truck / trailer — what records “who is using what”

| Store | Columns | Role today | Source of truth? |
|-------|---------|------------|------------------|
| **`trips`** | `driver_id`, `truck_id`, `trailer_id` | Movement assignment for execution | **Yes** for dispatch assignment (`app/models/trip.py` 52–59; `update_trip_assignment` `app/services/trips.py` 1159–1255) |
| **`trip_loads`** | membership load ↔ trip | Which loads are on the trip | Truth for membership; not equipment |
| **`loads`** | `driver_id`, `truck_id`, `trailer_id` | Historical / legacy mirror | **Legacy mirror** — Load API blocks writes (`app/services/loads.py` 175–182, `LOAD_ASSIGNMENT_FIELDS` `app/constants/trip_dispatch.py` 24) |
| **`loads`** | `active_trip_id` | Points at open **active** `trip_loads` row | Compatibility mirror (`app/services/trips.py` 490–508) |
| **`loads`** | `custody_*`, `custody_trailer_id` | Custody snapshot after events | Read-model; events in `load_custody_events` (`app/models/load.py` 112–127; `app/constants/custody.py`) |
| **`trucks` / `trailers`** | `owner_person_id`, `ownership_type` | Who owns asset (person, not driver) | Ownership truth; resolved via `driver.person_id` in hints (`app/routers/drivers.py` 160–186) |
| **`dispatch_trips`** | `load_id`, `trailer_move_id`, … | Legacy dispatch container | Legacy; linked from `trips.legacy_dispatch_trip_id` (`app/models/trip.py` 48–50). New Trip flows must not write `dispatch_trips` per product rules. |
| **Dedicated driver↔equipment binding table** | — | — | **Does not exist** |

**Assignment hints (suggestions, not SoT):** `GET /api/v1/drivers/{driver_id}/assignment-hints` (`app/routers/drivers.py` 129–188):

1. Latest **load** (not trip) with `Load.driver_id` and `Load.status` in legacy operational set (`_ASSIGNMENT_HINT_LOAD_STATUSES` lines 120–126), `order_by(Load.updated_at.desc())`, take `truck_id` / `trailer_id`.
2. Else first active **truck** where `Truck.owner_person_id == driver.person_id`.
3. Else first active **trailer** where `Trailer.owner_person_id == driver.person_id`.

**Truck→trailer pairing hint:** `GET /api/v1/trucks/{truck_id}/suggested-trailer` — latest **load** with that `truck_id` and non-null `trailer_id` (`app/routers/trucks.py` 71–82).

**Frontend:** `getDriverAssignmentHints` exists in `apps/web/src/api.ts` 2336–2340 but **no component calls it** (grep shows definition only). Trip workspace uses manual dropdowns (`TripWorkspacePage.tsx` 604–649).

---

## 3. Last trip trailer

### 3.1 Does a function/query exist?

**No** backend function returns “trailer on driver’s most recent **trip**.” Closest behaviors:

- Assignment hints: most recent **load** by `loads.updated_at` (`app/routers/drivers.py` 145–158).
- Dispatch home: `pickOpenTripForDriver` picks one **open** trip per driver from **listTrips** client-side (`apps/web/src/hooks/useDispatchHomeDashboard.ts` 117–126) — exposes `trip.truck` / `trip_number`, **not** trailer in the driver row (`buildDriverRows` 156–161).

### 3.2 Hypothetical SQL (not implemented as product API)

```sql
SELECT t.trailer_id
FROM trips t
WHERE t.tenant_id = :tenant_id
  AND t.driver_id = :driver_id
  AND t.trailer_id IS NOT NULL
  AND t.cancelled_at IS NULL
ORDER BY t.updated_at DESC   -- product rule not defined in code
LIMIT 1;
```

**“Most recent trip” is undefined** in code for trailer carry-over. Candidate order keys in schema: `trips.updated_at`, `trips.created_at`, `trips.completed_at`, `trips.status` — none wired for this rule.

### 3.3 Trip statuses (canonical `trips.status`)

From `app/constants/trip_dispatch.py` 57–62:

| Status | Constant |
|--------|----------|
| `planned` | `TRIP_CONTAINER_STATUS_PLANNED` |
| `assigned` | `TRIP_CONTAINER_STATUS_ASSIGNED` |
| `in_progress` | `TRIP_CONTAINER_STATUS_IN_PROGRESS` |
| `completed` | `TRIP_CONTAINER_STATUS_COMPLETED` |
| `cancelled` | `TRIP_CONTAINER_STATUS_CANCELLED` |

**DB (`tenant_demo`):** `SELECT DISTINCT status FROM trips` → only `assigned` (1 row) at query time.

Open-trip set used in UI: `OPEN_TRIP_STATUSES = planned, assigned, in_progress` (`useDispatchHomeDashboard.ts` 14–15).

---

## 4. Drop / hook trailer

### 4.1 Schema

`load_stop_actions.action_type` documents: `live_load`, `drop_trailer`, `hook_trailer`, `relay`, `yard_move` (`app/models/load.py` 218–225).

**DB (`tenant_demo`):** `SELECT COUNT(*) FROM load_stop_actions` → **0**; no rows by `action_type`.

### 4.2 API / services

Trip stop execution endpoints wired in `app/routers/trips.py`: arrival, departure, `unloading-started`, `unloading-completed` (e.g. 321–369) — **no** `drop_trailer` / `hook_trailer` routes found under `app/routers/`.

No matches for `drop_trailer` / `hook_trailer` in `app/services/` (grep).

### 4.3 Custody / yard (related, not “hook” vocabulary)

- Custody events: `yard_handoff`, `trip_accept_custody`, etc. (`app/constants/custody.py` 32–36).
- Routes: `POST .../accept-custody`, `yard-handoff`, `take-custody` (`app/authz/routes.py` 169–171).
- FMP: `POST /loads/{load_id}/yard-drop-instruction` (`app/routers/future_movement_plans.py` 125–133).

These update **load custody snapshot** (`custody_trailer_id`, etc.), not a dedicated “driver dropped trailer” flag consumed by assignment hints. **Dropping does not clear** assignment-hints data path (hints read **loads** in legacy statuses, not custody).

---

## 5. Assignment today — code paths and validation

### 5.1 Primary API

| Step | Method | Handler | Service |
|------|--------|---------|---------|
| Create trip + optional loads | `POST /api/v1/trips` | `app/routers/trips.py` 37–55 | `create_planned_trip` `app/services/trips.py` 632–682 |
| Set driver/truck/trailer | `PUT /api/v1/trips/{trip_id}/assignment` | `app/routers/trips.py` 418–439 | `update_trip_assignment` `app/services/trips.py` 1159–1255 |
| Optional schedule | `PUT /api/v1/trips/{trip_id}/schedule` | trips router | `update_trip_schedule` |
| Start execution | `POST /api/v1/trips/{trip_id}/execution-signal` | trips router | moves `assigned` → `in_progress` |

**Frontend:** `updateTripAssignment` → `apps/web/src/api.ts` 1514–1527; saved from `TripWorkspacePage.tsx` 423–445.

### 5.2 Validation in `update_trip_assignment`

| Check | Behavior | Code |
|-------|----------|------|
| Trip cancelled / completed | 409 | `trips.py` 1171–1176, 1182–1187 |
| Change assignment while `in_progress` | 409 `TRIP_ASSIGNMENT_LOCKED_IN_PROGRESS` | 1178–1188 |
| Driver/truck/trailer exist in tenant | 404 | `_validate_assignment_targets` 436–455 |
| Schedule overlap | 409 `TRIP_ASSIGNMENT_SCHEDULE_OVERLAP` only vs other **`in_progress`** trips when **this** trip has `planned_start_at` and other has `expected_completion_at` | `_validate_decision10_schedule_overlap` 1112–1156 |
| Driver already on another **planned/assigned** open trip | **No check** | — |
| Warning vs error for double booking | **Hard error** only for overlap case above; **no warning** response shape | tests `tests/test_trip_assignment_issue15_issue16.py` |

**Promotion to `assigned`:** when all three IDs non-null, sets `assigned_at` and `planned` → `assigned` (`trips.py` 1214–1222).  
`POST /trips` may prefill IDs but leaves `assigned_at` null and status `planned` (`create_planned_trip` 667–670, 1214–1225).

### 5.3 Creating trip + driver in one call?

**Partially.** `POST /trips` accepts optional `driver_id`, `truck_id`, `trailer_id`, `load_ids` (`CreatePlannedTripBody` `app/schemas/trip_read.py` 107–123).  
**Load workspace UI** only sends `load_ids` (no driver) — `LoadWorkspacePage.tsx` 440–444.

**Typical multi-call flow today:**

1. `POST /api/v1/trips` with `{ status: "planned", job_type: "freight_load", load_ids: [loadId] }`
2. `PUT /api/v1/trips/{id}/assignment` with `{ driver_id, truck_id, trailer_id }` (all keys required; null clears)

Optional: `PUT .../schedule`, then `POST .../execution-signal` for in_progress.

**Single-call alternative (API only):** `POST /trips` with all three IDs + `load_ids` still creates **`planned`** until `PUT .../assignment` completes triple (`assigned_at` / status promotion logic in `update_trip_assignment` only).

### 5.4 Load-level assignment

**Blocked:** `_reject_load_assignment_fields` `app/services/loads.py` 175–182.

Load form assignment section is read-only (`LoadWorkspaceForm.tsx` 588–607).

---

## 6. Driver state for the picker (Dispatch home)

### 6.1 APIs used

`useDispatchHomeDashboard` (`apps/web/src/hooks/useDispatchHomeDashboard.ts` 314–366):

| Data | API | Limit |
|------|-----|-------|
| Drivers | `listDrivers` → `GET /api/v1/drivers` | 80 |
| Trips | `listTrips` | page 1, size 80 |
| Unassigned loads | `listLoads({ dispatch_unassigned: true })` → `GET /api/v1/loads?dispatch_unassigned=true` | 50 |
| FMP | `listFutureMovementPlans` | 50 |

Backend unassigned definition: `list_dispatch_unassigned_loads` `app/services/loads.py` 787–818 — `status` in `ready` \| `unassigned`, `active_trip_id` null, no open planned `trip_loads`, no open FMP line.

### 6.2 What driver rows include

`buildDriverRows` (`useDispatchHomeDashboard.ts` 128–169):

- Name, availability bucket (`available` \| `executing` \| `scheduled` \| `unverified` \| `license_blocked`)
- `truckLabel` from **open trip’s** `truck.unit_number` only (`Trk {unit}`)
- `tripNumber` if open trip exists
- License warning text

**Missing for “Singh - Boston - Trailer 5307 - available”:**

| Desired | Present? |
|---------|----------|
| Last delivery **city** | **No** (no geolocation / last stop in driver list) |
| **Trailer** on driver row | **No** (truck only from open trip) |
| Default truck for long-haul | **No** in list API |
| `driver_operating_subtype` | **No** on `DriverListOut` / list endpoint |
| Confident “available” | Partial — derived from open trip list; may be `unverified` if trip list truncated (`tripsFetchMayBeIncomplete` 286–288) |

### 6.3 Drag-assign on Dispatch home

**Not implemented.** Queue rows navigate via links (`DispatchHomeDashboard.tsx` 200–227). Static mock text “Drag load to driver” exists only in legacy `app/static/dashboard/index.html` 103 — not wired to React dispatch home.

---

## 7. Gaps table (owner rules vs reality)

| Rule (owner intent) | DB | API | UI | Missing |
|---------------------|----|-----|-----|---------|
| Long-haul **default truck** (until breakdown) | No `default_truck_id` on driver; optional `owner_person_id` on truck | Hints: owner truck only (`drivers.py` 160–172) | No default truck display | Persistent default truck + breakdown override |
| **City driver** — no own truck; dispatch picks truck+trailer | `driver_operating_subtype=city_local` in `driver_person_extensions` | Subtype not on driver list; hints still query owner truck | No city-specific picker UX | Policy wiring subtype → skip owner-truck hint |
| **Trailer carry-over** from driver’s last trip | `trips.trailer_id` stored per trip | No last-trip-trailer endpoint | No prefill on assign (hints API unused) | Defined “most recent trip” + drop awareness |
| **Drop** clears hooked trailer | `load_stop_actions` types exist; 0 rows on demo | No drop/hook writers | No drop/hook UI | Event model + assignment integration |
| **Busy driver** → warning not block | Multiple open trips possible | No duplicate-driver check; overlap 409 only for in_progress schedule | Dispatch shows `scheduled`/`executing`, no warn on assign save | Warning path on assign |
| **Auto trip** on assign driver to ready load | `POST /trips` + membership | Supported server-side | User must click **Create Planned Trip** then assign (`LoadWorkspacePage.tsx` 428–445) | One-step assign+trip from load or dispatch drag |

---

## 8. Dispatcher step count (current screens)

Assumes load is already **`ready`** (e.g. parse → Create load). Draft/email path adds **Mark ready** before dispatch.

| # | Action | Where |
|---|--------|--------|
| 1 | Open **Dispatch** (`/dashboard`) | `DispatchHomeDashboard` |
| 2 | Click unassigned load in **Loads to assign** (opens load workspace `/loads/{id}`) | `DispatchHomeDashboard.tsx` 200–207; `useDispatchHomeDashboard.ts` 205–219 |
| 3 | Click **Create Planned Trip →** | `LoadWorkspacePage.tsx` 2191–2198 → `createPlannedTrip` 440–445 |
| 4 | (Auto) Navigate to **Trip workspace** `/trips/{id}` | `LoadWorkspacePage.tsx` 445 |
| 5 | Open **Update assignment** — choose **Driver** | `TripWorkspacePage.tsx` 604–625 |
| 6 | Choose **Truck** | 627–641 |
| 7 | Choose **Trailer** | 643–649 |
| 8 | **Save** assignment (`PUT .../assignment`) | `TripWorkspacePage.tsx` 423–445 |

**Count:** **8** numbered dispatcher actions from ready load on dispatch queue to driver+truck+trailer saved on trip.

**Not in path:** drag-drop; driver picker on load/parser page; auto-fill trailer; confirming execution (**Start Execution** is a separate optional step after assigned).

**Alternate entry:** Trips list → open planned trip needing driver/equipment (`buildAssignQueue` `useDispatchHomeDashboard.ts` 246–277) — same assignment steps 5–8, different navigation to trip id.

---

## References (quick index)

- Trip assignment service: `app/services/trips.py` 1159–1255  
- Trip assignment route: `app/routers/trips.py` 418–439  
- Load assignment write block: `app/services/loads.py` 175–182  
- Driver assignment hints: `app/routers/drivers.py` 120–188  
- Dispatch unassigned loads: `app/services/loads.py` 717–818, `app/routers/loads.py` 88–96  
- Operator “Unassigned” label: `apps/web/src/loads/operatorLoadStatus.ts` 68–69  
- Trip statuses: `app/constants/trip_dispatch.py` 57–62  
