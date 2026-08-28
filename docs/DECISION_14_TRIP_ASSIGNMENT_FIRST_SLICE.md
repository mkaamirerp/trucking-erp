# TruckERP — Decision 14 / Trip Assignment Update (first implementation slice)

**Status:** **LOCKED + SHIPPED / IMPLEMENTED** — the first post–Slice-1 Trip assignment slice is in the codebase.  
**Current code:** `PUT /api/v1/trips/{trip_id}/assignment` updates Trip-level driver/truck/trailer assignment, promotes `planned` → `assigned` when the required assignment is complete, writes Trip audit history, and does **not** revive `Load.status = dispatched` or write `dispatch_trips`.  
**Document-use note:** The detailed body below is preserved as the **pre-implementation scope/acceptance record**. Wording such as “implementation follows,” “before coding,” or “Trips do not yet emit audit_events” is historical planning context, not current shipped-state truth. For current cross-slice execution/custody status, use `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`.

**Depends on (merged):** PR **#31** / legacy dispatch cutover Slice 1 (`7012f40a` + docs), **Decision 6** (Load workspace actions), **Decision 7** (active execution signal — implemented separately after this slice), **Decision 9** (planning queue), **Decision 10** (future assignment guard — not fully implemented here unless explicitly added later), **Decisions 11–13** (readiness/custody/exception principles — later slices own those behaviors), **`PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`**, **`PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`**.

**Related:** `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `PHASE3L_D_OWNER_DECISION_CHECKLIST.md`.

---

## A. Slice name

**Trip Assignment Update Slice**

---

## B. Purpose

After blocking **new** generic **`Load.status → dispatched`** trip minting (Slice 1), the **smallest safe** next step is a **dedicated trip assignment API** so dispatch can commit **driver / truck / trailer** on a **planned trip container** without using legacy load status, without starting **execution**, **custody**, or **payroll**.

---

## C. What this slice implements

### C.1 Backend

- **`PUT /api/v1/trips/{trip_id}/assignment`**
- Updates **`trips.driver_id`**, **`trips.truck_id`**, **`trips.trailer_id`** (subject to validation rules below).
- **May set `trips.assigned_at`** when assignment is **first completed** (define “completed” in implementation: e.g. all three IDs non-null and validated, first time transitioning from no committed assignment to a full set — document precisely in service code).
- **May transition `Trip.status` from `planned` → `assigned`** **only if** the trip satisfies **required assignment fields** for that promotion (product rule: e.g. all three resources present and tenant-valid; do not promote on partial unless a later decision explicitly allows partial **assigned**).
- **Does not** create **execution** or **custody** events (no `load_custody_events`, no pickup/delivery/terminal/handoff records).
- **Does not** add **`dispatch_trips`** rows and **does not** mint trip numbers via this endpoint.
- **Does not** change **`Load.status`**, including **never** setting **`Load.status = dispatched`** from this path.
- **Does not** implement **`POST …/transition`** for **`in_progress`** / **`completed`**.

**RBAC follow-up:** this slice follows existing trip route auth style. Future trip-operation permissions should explicitly gate assignment updates.

### C.2 Audit (see section H)

- Record each successful assignment change with **actor**, **timestamps**, and **before/after** (or **`changed_fields`**) via the **preferred** mechanism in section **H**.

### C.3 Frontend

- **Primary UI:** **Trip detail / Trip workspace** — controls to set driver, truck, trailer and call **`PUT …/assignment`**.
- **Load Workspace:** May **link** or **navigate** to the trip assignment flow (e.g. when **`loads.active_trip_id`** is set). It **must not** imply that **`Load.status`** drives dispatch commitment for new work.
- **Out of scope:** Full **Decision 6** action bar (**Assign & Send**) in one control — see section **D**.

---

## D. Explicitly out of scope (later slices)

| Topic | Reason |
|-------|--------|
| **Assign & Send** | Requires **driver dispatch package**, **versioning**, and send semantics (**Decision 8** draft; **Decision 6** composite). **Later slice.** |
| **Custody** | **Decision 12** — no **`terminals`**, **`load_custody_events`**, pickup/delivery/handoff events in this slice. |
| **Execution state machine** | **`assigned` → `in_progress` → `completed`** and execution signals (**Decision 7**) — **later.** |
| **Payroll / `review_required`** | **Decision 13** — **later.** |
| **Recovery / repower** | **Decision 13** — new trip + custody chain — **later.** |
| **`Load.status` target enforcement** | **Decision 11** cleanup (draft/ready/cancelled writes, board migration) — **not** this slice; only **preserve** Slice 1 behavior. |
| **Decision 10 enforcement** | Scheduling conflict + supervisor override — **optional** later enhancement; **not required** to ship this slice. |

---

## E. Load.status and legacy dispatch (must preserve Slice 1)

- **No** new path to **`Load.status = dispatched`** from this slice.
- **No** **`dispatch_trips`** minting from **generic `Load` PATCH** — Slice 1 remains authoritative (**`409`**, **`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`** for **`source != "seed"`**).
- **`PUT` trip assignment** must **not** call **`loads_service.update_load`** (or equivalent) to change load status to **`dispatched`**.

---

## F. Safety rules (must not)

This slice **must not**:

- Mark pickup, delivered, en route, or **start custody**.
- Trigger **payroll**, settlement, or **`review_required`** automation.
- Silently change **broker / commercial** load fields (rates, customer refs, etc.) — **assignment only** on **`trips`**.
- **Overwrite** assignment in a **recovery** pattern (swap driver on same trip for repower) — **Decision 13** requires a **new** trip; that workflow is **out of scope**; do not implement recovery UX here.
- Create **false** movement / mileage / ELD history.
- **Create or update `dispatch_trips`** from **`Trip.status`** or from this assignment endpoint (**v1** guardrail per **3L-C**).
- Reintroduce **`Load.status → dispatched`** as the execution trigger for new work.

---

## G. Migration risk

| Topic | This slice |
|-------|------------|
| **`trips` columns** | **`driver_id`**, **`truck_id`**, **`trailer_id`**, **`assigned_at`** already exist on **`trips`** — **no** new trip-column migration required for assignment-only updates. |
| **Audit** | If using **`audit_events`** (section **H**), tenant DB must have **`audit_events`** from existing tenant migration (`alembic_tenant` audit foundation). **No new table** if reusing **`audit_events`**. |
| **New `trip_assignment_events` table** | **Not required** for this slice if **`audit_events`** is used — avoids extra Alembic. |
| **Backward compatibility** | **Additive** API; existing **`POST /trips`** create with optional assignment unchanged. |
| **Legacy / demo** | **`source="seed"`** load paths remain **internal only** per Slice 1; assignment endpoint is normal API (**`source`** as **`audit_events`** field, not load patch). |

---

## H. Audit strategy (pre-implementation inventory — historical)

> **Historical planning section:** assignment audit is now shipped. This section is retained to explain why `audit_events` was chosen over a dedicated `trip_assignment_events` table.

### H.1 What existed before this slice

- **Tenant table:** **`audit_events`** (append-only), model **`app.models.tenant.AuditEvent`**, writer **`app.services.audit_events.write_audit_event`**.
- **Tenant migration:** `alembic_tenant/versions/s1b2c3d4e5f6_audit_events_foundation.py` (and successors if any).
- At design time, **`write_audit_event`** was already wired for Loads and People while Trip assignment had not yet adopted it. The shipped assignment slice now writes Trip audit history.

### H.2 Decision for Trip Assignment Update Slice

**Reuse `audit_events`** for assignment changes:

- Call **`write_audit_event`** with e.g. **`module="trips"`** (or **`"dispatch"`** — pick one and keep consistent), **`entity_type="trip"`**, **`entity_id=str(trip_id)`**, **`action`** such as **`trip_assignment_updated`**, **`source="api"`** (or **`ui`** when called from UI-backed requests), **`actor_user_id`** from auth, and **`changed_fields`** and/or **`snapshot_before` / `snapshot_after`** for driver/truck/trailer (and **`assigned_at`** / **`status`** if changed).
- **Tenant-safe:** **`tenant_id`** is required on every row; indexes support **`(tenant_id, entity_type, entity_id, …)`** queries.
- **`best_effort=True`** (default) avoids failing the assignment if audit insert fails — align with product: log and monitor; optionally **`best_effort=False`** in staging if strict audit is required.

**`trip_assignment_events` (dedicated table):** **Not required** for this slice. Reserve for a **future** slice only if query patterns need **stronger** trip-specific constraints or **timeline** APIs before a unified timeline merges **`audit_events`** + custody.

### H.3 Alembic for audit

- **If** **`audit_events`** is **already present** in target tenant DBs — **no new Alembic** for audit in this slice.
- **If** a tenant DB is **behind** on tenant migrations — **upgrade tenant** to include **`audit_events`** (existing migration) **before** enabling audit writes; that is **operational**, not a new schema for assignment.
- **If** implementers later choose a **new** **`trip_assignment_events`** table instead — that **would** require **new tenant Alembic**; **Decision 14** **does not** require that path.

---

## I. Tests required (implementation acceptance)

**Backend (pytest):**

1. **`PUT` assignment — happy path** — updates trip equipment; optional assert **`planned` → `assigned`** when rules met; **`assigned_at`** set when appropriate.
2. **Invalid trip** — wrong id / 404.
3. **Cancelled trip** — reject assignment (**4xx**; exact code in implementation).
4. **Wrong-tenant** driver/truck/trailer — reject.
5. **Assignment does not create `dispatch_trips`** — assert no new row / no unexpected mint side effects.
6. **Assignment does not set `Load.status = dispatched`** — for member loads, status unchanged by assignment endpoint alone.

**Frontend:**

7. **`cd apps/web && npm run build`** — must pass in CI / pre-merge.

**Optional but recommended:** assert **`audit_events`** row (or count) when audit is enabled and DB available in test harness.

---

## J. Summary

| Item | Lock |
|------|------|
| **Slice name** | **Trip Assignment Update Slice** |
| **API** | **`PUT /api/v1/trips/{trip_id}/assignment`** |
| **Data touched** | **`trips.driver_id`**, **`truck_id`**, **`trailer_id`**, **`assigned_at`** (when first completed), **`status`** (**`planned` → `assigned`** only when required fields satisfied) |
| **Custody / terminals** | **None** |
| **Assign & Send** | **Deferred** |
| **Load.status** | **No change**; Slice 1 **`dispatched`** block preserved |
| **Audit** | **`audit_events` + `write_audit_event`**; **`trip_assignment_events`** **not** required |
| **Alembic (typical)** | **None** for assignment + audit_events path if tenant already migrated |

---

*End of Decision 14 — Trip Assignment Update Slice.*
