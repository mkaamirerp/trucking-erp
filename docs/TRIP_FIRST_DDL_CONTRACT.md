# TruckERP — Trip-First DDL Contract

## 0) Purpose

This document turns the Trip-first schema foundation into a stricter DDL-style implementation contract for Cursor.

Its purpose is to reduce ambiguity before coding by locking:

* table list
* field list
* nullability direction
* foreign key direction
* uniqueness/index direction
* enum/value direction
* authority vs snapshot distinction
* migration-safe transitional fields

This is still not literal migration code.
But it is intentionally close enough that Cursor should not invent architecture on its own.

This contract focuses on the V1 core needed to move from load-first operations toward trip-first operations.

---

## 1) Core DDL design rules

### 1.1 Tenant scope

Every business table in tenant DB must remain tenant-scoped.

### 1.2 Authority separation

* `trips` = authoritative operational container
* `trip_loads` = authoritative trip↔load membership
* `loads` = authoritative commercial/load contract record
* transitional snapshot fields may exist, but must be clearly marked as non-authoritative

### 1.3 No fake simplification

Do not collapse the model into:

* one `trip_id` on `loads` as the only relationship truth
* one `trip_number` on `loads` as the only trip identity source
* one load row pretending to be both commercial record and operational container

### 1.4 Migration-safe approach

V1 may keep some legacy convenience/snapshot fields on `loads`, but business logic must stop treating them as authoritative once `trips` and `trip_loads` are introduced.

---

## 2) Required V1 tables

The minimum DDL contract for the Trip-first shift is:

1. `trips`
2. `trip_loads`
3. update/clarify `loads`
4. keep `load_stops` authoritative for contractual stops

Near-following tables, not required for the very first migration but must remain compatible with this contract:

* `trip_events`
* `trip_stops`
* `load_custody_events`

---

## 3) Table: `trips`

### 3.1 Purpose

Authoritative operational execution container—and **scheduling/planning shell** before execution.
Represents one real-world movement assignment (or **planned** movement) under **one trip number** minted at **Trip create**.

A Trip may exist **without** driver/truck/trailer and **without** any **active** `trip_loads` rows temporarily; see [`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md) and [`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md) §11.1.

### 3.2 Required columns

#### Identity / scope

* `id` — UUID or bigint, match tenant DB convention, primary key, not null
* `tenant_id` — FK / tenant scope column, not null

#### Operational identity

* `trip_number` — string/varchar, not null
* `status` — string/enum, not null
* `completion_policy` — string/enum, not null, default tenant/business default
* `dispatch_mode` — string/enum, nullable initially

#### Assignment

* `driver_id` — FK to drivers or people/driver projection used by current tenant model, nullable
* `secondary_driver_id` — FK, nullable
* `truck_id` — FK to trucks/assets, nullable
* `trailer_id` — FK to trailers/assets, nullable

#### Routing / terminal context

* `origin_terminal_id` — FK nullable
* `target_terminal_id` — FK nullable

#### Timing

* `started_at` — timestamptz / datetime, nullable
* `completed_at` — timestamptz / datetime, nullable
* `cancelled_at` — timestamptz / datetime, nullable

#### Notes / audit

* `notes` — text, nullable
* `created_at` — timestamptz, not null
* `updated_at` — timestamptz, not null
* `created_by` — FK/user reference nullable or not-null depending on existing pattern
* `updated_by` — FK/user reference nullable if consistent with current codebase

### 3.3 Required constraints

* PK on `id`
* unique `(tenant_id, trip_number)`
* check/enum constraint on `status`
* check/enum constraint on `completion_policy`
* check/enum constraint on `dispatch_mode` if using DB-level check in V1

### 3.4 Recommended indexes

* index `(tenant_id, status)`
* index `(tenant_id, driver_id)`
* index `(tenant_id, truck_id)`
* index `(tenant_id, trailer_id)`
* index `(tenant_id, target_terminal_id)`
* index `(tenant_id, started_at)`

### 3.5 Authority note

`trip_number`, driver/truck/trailer assignment, and trip operational status are authoritative here.
They must not remain authoritative on `loads`.

---

## 4) Enum contract: `trips.status`

### Required V1 values

* `draft`
* `planned`
* `assigned`
* `dispatched`
* `in_progress`
* `arrived_terminal`
* `handed_off`
* `completed`
* `cancelled`

### Notes

* `draft` / `planned`: Trip container may have **zero active** `trip_loads` (planning shell); **`trip_number` still minted at create** per dispatch rule doc.
* `arrived_terminal` and `handed_off` may be introduced in first pass if useful; if rollout wants fewer values initially, they can still be reserved in shared enums now.
* Trip status is operational only. Do not use it to represent commercial close/invoice/payment concepts.
* **`cancelled`:** set with **`cancelled_at`** when column exists; **does not** delete row; **does not** recycle **`trip_number`**.

---

## 5) Enum contract: `trips.completion_policy`

### Required V1 values

* `final_delivery`
* `assignment_complete`

### Notes

Do not overdesign “empty trailer” logic into a hard system-wide completion mode at DDL stage.
That can later be modeled as tenant policy/workflow logic if needed.

---

## 6) Enum contract: `trips.dispatch_mode`

### Required V1 values

* `direct_delivery`
* `terminal_dispatch`

### Rule

If `dispatch_mode = terminal_dispatch`, application/service layer should require `target_terminal_id`.

### Note

This is routing intent, not a replacement for later trip stops or custody events.

---

## 7) Table: `trip_loads`

### 7.1 Purpose

Authoritative membership link between trips and loads.

### 7.2 Required columns

#### Identity / scope

* `id` — UUID or bigint, primary key, not null
* `tenant_id` — scope column, not null

#### Link columns

* `trip_id` — FK to `trips.id`, not null
* `load_id` — FK to `loads.id`, not null

#### Relationship state

* `status_within_trip` — string/enum, not null, default `active` or `planned` depending on service flow
* `sequence_hint` — integer nullable
* `notes` — text nullable

#### Timing / audit

* `added_at` — timestamptz, not null
* `removed_at` — timestamptz, nullable
* `created_at` — timestamptz, not null
* `updated_at` — timestamptz, not null
* `created_by` — FK/user reference nullable or per existing pattern
* `updated_by` — FK/user reference nullable

### 7.3 Required constraints

* PK on `id`
* FK `trip_id -> trips.id`
* FK `load_id -> loads.id`
* check/enum constraint on `status_within_trip`

### 7.4 Required uniqueness / active-membership rule

At minimum, prevent duplicate active membership of the same load in the same trip.

#### Recommended pattern

Unique partial index or equivalent logic such as:

* unique `(tenant_id, trip_id, load_id)` where `removed_at is null`

### 7.5 Recommended indexes

* index `(tenant_id, trip_id)`
* index `(tenant_id, load_id)`
* index `(tenant_id, status_within_trip)`

### 7.6 Authority note

This table is the authoritative answer to:

* which loads belong to a trip
* whether that membership is currently active

Do not let `loads.trip_id` or similar convenience fields replace this truth.

---

## 8) Enum contract: `trip_loads.status_within_trip`

### Required V1 values

* `planned`
* `active`
* `completed`
* `removed`

### Notes

* `removed` / `completed` / `planned` / `active`: encode **membership** and sequence in trip, **not** the full commercial meaning of the Load.
* **Load commercial cancellation** is **`loads.status`** (or explicit cancel vocabulary). **Closing membership** on **`trip_loads`** (e.g. `removed_at`, `status_within_trip`) **must not** imply Trip cancel unless separate trip workflow runs.
* Keep this modest in V1. Do not try to encode all custody/handoff semantics here. Those belong in later event/custody tables.

---

## 9) Table: `loads` — authoritative role after redesign

### 9.1 Purpose

First-class commercial/broker/customer contract record.
Not replaced.
Not deprecated.
But no longer the authoritative operational root.

### 9.2 Loads remain authoritative for

* broker linkage / broker snapshots
* broker contact linkage / snapshot
* rate confirmation identity/data
* commercial references
* commodity / weight / temp / equipment requirement
* load-specific notes and documents
* billing/invoice-facing identity
* contractual stop ownership

### 9.3 Loads stop being authoritative for

* trip number
* operational driver assignment
* operational truck assignment
* operational trailer assignment
* operational movement container truth

---

## 10) Table: `loads` — transitional DDL rules

This section does not redefine the whole existing `loads` table. It defines what must happen to key fields conceptually.

### 10.1 Fields that should no longer be authoritative

If present today, these become legacy/snapshot-only or should be retired over time:

* `trip_number`
* `driver_id` as dispatch truth
* `truck_id` as dispatch truth
* `trailer_id` as dispatch truth
* any single-field representation that implies load itself is the operational container

### 10.2 Allowed transitional convenience fields on `loads`

These may exist temporarily if helpful during migration:

* `active_trip_id` — FK nullable
* `trip_number_snapshot` or existing `trip_number` as display snapshot only
* `current_driver_id_snapshot` nullable
* `current_truck_id_snapshot` nullable
* `current_trailer_id_snapshot` nullable

### 10.3 Strong recommendation on naming

If snapshot fields are added new, use names that make snapshot/non-authority explicit.
If legacy names remain for compatibility, service docs/tests must clearly mark them as non-authoritative.

### 10.4 Required index if `active_trip_id` is added

* index `(tenant_id, active_trip_id)`

### 10.5 Authority note

If `loads.active_trip_id` exists, it is for convenience/navigation only.
Authoritative relationship truth remains `trip_loads`.

---

## 11) Table: `loads` — status boundary rule

### Rule

Load status and Trip status are separate concepts.

### Implication

Do not make `loads.status` carry the whole operational meaning of a trip.
Examples of things that should not rely only on `loads.status` after redesign:

* whether a driver is currently dispatched
* which truck/trailer is active on the movement
* which trip number is active

### Recommended direction

Keep current load status shape if necessary for migration, but do not expand it into a replacement for trip execution state.

**Commercial load cancellation** (when represented in `loads.status` or a dedicated cancel flag) **must not** auto-set **`trips.status = cancelled`**. **Manual Trip cancel** is a separate dispatcher action and closes **`trip_loads`** active memberships without auto-cancelling Loads unless explicitly designed. See [`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md) §11.1.

## 12) Table: `load_stops`

### Purpose

Contractual stop truth for a load.

### DDL contract

No immediate redesign required in this first trip-first migration, but the table remains authoritative for:

* stop ownership by load
* references/appointments tied to the load
* contractual stop sequence within the load’s business record

### Rule

Do not repurpose `load_stops` to be the final operational sequence engine for multi-load trip execution.

### Compatibility note

Future `trip_stops` / `trip_stop_load_links` must be able to coexist with `load_stops` cleanly.

---

## 13) Optional transitional field: `loads.active_trip_id`

### Recommendation

Add only if it materially helps migration and UI navigation.
Do not add it just because it feels familiar.

### If added

* type matches `trips.id`
* nullable
* FK to `trips.id`
* indexed

### Purpose

* current active trip navigation
* list/detail performance
* easier bridge from existing load screens

### Strict rule

This is a convenience pointer only.
Services must not derive authoritative membership from it alone.

---

## 14) Future-compatible reserved tables (not required in first DDL pass, but this contract must not block them)

### 14.1 `trip_events`

Purpose: trip timeline / audit-safe operational event history.

### 14.2 `trip_stops`

Purpose: operational execution sequence at trip level.

### 14.3 `load_custody_events`

Purpose: handoff / staging / trailer transfer / continuity across trips.

### Important compatibility rule

Nothing in the first DDL migration should make these impossible or awkward later.

---

## 15) Foreign key direction rules

### Trips

* `driver_id` -> current operational driver table/projection in tenant DB
* `secondary_driver_id` -> same family as above
* `truck_id` -> trucks/assets table
* `trailer_id` -> trailers/assets table
* `origin_terminal_id` / `target_terminal_id` -> terminal/location entity when available

### TripLoads

* `trip_id` -> `trips.id`
* `load_id` -> `loads.id`

### Loads convenience pointer if used

* `active_trip_id` -> `trips.id`

### Rule

Do not attempt cross-DB or platform-side relationships here. This is tenant DB operational data.

---

## 16) Nullability rules

### Trips

Allow nullable assignment/routing fields in draft/planned stages:

* `driver_id` nullable
* `secondary_driver_id` nullable
* `truck_id` nullable
* `trailer_id` nullable
* `origin_terminal_id` nullable
* `target_terminal_id` nullable
* `started_at` nullable
* `completed_at` nullable
* `cancelled_at` nullable

Do **not** allow null for:

* `tenant_id`
* `trip_number`
* `status`
* `completion_policy`
* `created_at`
* `updated_at`

### TripLoads

Do **not** allow null for:

* `tenant_id`
* `trip_id`
* `load_id`
* `status_within_trip`
* `added_at`
* `created_at`
* `updated_at`

Allow null for:

* `removed_at`
* `sequence_hint`
* `notes`

### Loads convenience fields if present

* `active_trip_id` nullable
* snapshot assignment fields nullable

---

## 17) Unique / check / partial-index contract

### Trips

* `unique (tenant_id, trip_number)`
* check or enum constraint on `status`
* check or enum constraint on `completion_policy`
* check or enum constraint on `dispatch_mode` if stored as text

### TripLoads

* partial unique preventing duplicate active membership:

  * `unique (tenant_id, trip_id, load_id) where removed_at is null`
* check or enum constraint on `status_within_trip`

### Loads

* no unique/index change required by this contract except optional `active_trip_id` index

---

## 18) Authority map that Cursor must follow

### Authoritative on `trips`

* trip number
* operational movement identity
* operational driver/team assignment
* operational truck assignment
* operational trailer assignment
* dispatch mode / terminal routing intent
* trip operational status

### Authoritative on `trip_loads`

* trip↔load membership
* active vs removed membership state
* relationship continuity between trip and load

### Authoritative on `loads`

* broker/commercial identity
* rate confirmation and references
* commodity/requirements
* documents
* contractual stops
* commercial-facing truth

### Non-authoritative / transitional only on `loads`

* active trip pointer
* snapshot trip number
* snapshot driver/truck/trailer values

---

## 19) Migration DDL sequence

### Step 1

Create `trips` table with all required constraints/indexes.

### Step 2

Create `trip_loads` table with active-membership uniqueness rule.

### Step 3

Optionally add `loads.active_trip_id` nullable FK + index if migration/UI wants it.

### Step 4

Do **not** immediately drop legacy operational-ish fields from `loads`.
Instead, mark them as transitional in code/docs/tests and shift service authority first.

### Step 5

After service layer is writing through `trips`/`trip_loads`, begin demoting load-root operational assumptions in UI/API.

### Step 6

Only later consider removal/renaming of legacy load operational fields if safe.

---

## 20) Cursor guardrails

Cursor should not do any of the following:

### 20.1 Bad pattern

Add `trips` but keep generating/reading trip number primarily from `loads`.

### 20.2 Bad pattern

Use `loads.driver_id` / `loads.truck_id` / `loads.trailer_id` as the real live operational source after introducing `trips`.

### 20.3 Bad pattern

Skip `trip_loads` and replace it with only `loads.active_trip_id`.

### 20.4 Bad pattern

Repurpose `load_stops` as the full trip execution model.

### 20.5 Bad pattern

Treat terminal dispatch as a notes-only concept instead of trip-level routing intent.

---

## 21) DDL-ready canonical summary

### Table: `trips`

Required columns:

* `id`
* `tenant_id`
* `trip_number`
* `status`
* `completion_policy`
* `dispatch_mode` nullable
* `driver_id` nullable
* `secondary_driver_id` nullable
* `truck_id` nullable
* `trailer_id` nullable
* `origin_terminal_id` nullable
* `target_terminal_id` nullable
* `started_at` nullable
* `completed_at` nullable
* `cancelled_at` nullable
* `notes` nullable
* `created_at`
* `updated_at`
* `created_by` nullable/per pattern
* `updated_by` nullable/per pattern

Required constraints:

* PK on `id`
* unique `(tenant_id, trip_number)`
* checks/enums for `status`, `completion_policy`, optional `dispatch_mode`

### Table: `trip_loads`

Required columns:

* `id`
* `tenant_id`
* `trip_id`
* `load_id`
* `status_within_trip`
* `sequence_hint` nullable
* `notes` nullable
* `added_at`
* `removed_at` nullable
* `created_at`
* `updated_at`
* `created_by` nullable/per pattern
* `updated_by` nullable/per pattern

Required constraints:

* PK on `id`
* FK to `trips`
* FK to `loads`
* active-membership unique rule
* check/enum on `status_within_trip`

### Table: `loads`

Keep existing table.
Do not remove commercial authority.
Demote operational fields from authoritative status.
Optional:

* `active_trip_id` nullable FK/index as convenience only

---

## 22) Final locked DDL principles

1. **`trips` must become the authoritative operational container table.**
2. **`trip_loads` must exist as an explicit membership table.**
3. **`loads` must remain first-class and keep commercial authority.**
4. **Trip number authority must move to `trips`.**
5. **Operational driver/truck/trailer assignment authority must move to `trips`.**
6. **Any trip-related fields left on `loads` are transitional/snapshot only.**
7. **`load_stops` remain contractual stop truth and are not the final trip execution model.**
8. **DDL must stay compatible with later `trip_events`, `trip_stops`, and `load_custody_events`.**
9. **Terminal dispatch must be representable at trip level through `dispatch_mode` and terminal reference.**
10. **Cursor must not reintroduce load-first operational authority through legacy field habits.**

---

## 23) Next document after this one

After this DDL contract, the next strict implementation note should define:

* exact migration names / Alembic sequence
* exact Postgres types and enum strategy
* exact save/commit API contract between LoadWorkspacePage and TripWorkspacePage
* **trip number generation: mint on `trips` plan/create** (single pool with `tenant_dispatch_numbering`); alignment with legacy **`dispatch_trips`** during dual-write
* exact backfill strategy for existing live data
* **manual Trip cancel** API and **membership close** rules vs **Load cancel**

