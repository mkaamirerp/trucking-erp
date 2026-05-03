# Planned Trip Lifecycle — Module Close Report

Scope: Phases 3D–3J + mirror alignment commit, as delivered on `main`.

Constraints for this document: No product code changes; 3K not started.

## 1. Final git state

| Item | Value |
|---|---|
| Current branch | `main` |
| Tracking | `main` aligned with `origin/main` at time of check |
| HEAD | `397c0174` — `feat(trips): cancel planned trip from trip workspace` |
| Working tree | Clean at module close |

Latest 7 commits, newest first:

```text
397c0174 feat(trips): cancel planned trip from trip workspace
84f752b1 feat(trips): add load search picker to trip workspace
4d356230 feat(trips): remove load from planned trip workspace
4b554d5a feat(trips): add load to planned trip from trip workspace
4ca3f9ad fix(trips): expose and sync active trip mirror on loads
adee49b1 feat(trips): create planned trip from load workspace
3fac7d31 feat(trips): add read-only trip list and detail UI
```

Prior foundation:

```text
71cb2bc0 feat(trips): Phase 3D planned trip API and runtime proof
86069e09 feat(trips): add phase 1 trip container foundation
```

## 2. Feature inventory

### 3D — Planned trip backend API (`71cb2bc0`)

| Field | Detail |
|---|---|
| Commit | `71cb2bc0` |
| Files touched | Tenant migrations for trips/trip_loads/mirror catch-up, `app/models/trip.py`, `app/constants/trip_dispatch.py`, `app/routers/trips.py`, `app/schemas/trip_read.py`, `app/services/trips.py`, `app/services/dispatch_trips.py`, `app/services/trip_mirror_catchup.py`, `app/main.py`, `scripts/phase3d_runtime_proof.py`, `tests/test_trip_phase3d_planned_actions.py`, `tests/test_trip_read_detail.py`, etc. |
| Behavior | Planned trip container operations: create, list, detail, add/remove membership, cancel; shared trip numbering via tenant dispatch numbering; `trips.cancelled_at`; integration tests + runtime proof script. |
| Proof | Repo tests + `phase3d_runtime_proof.py`; CI/host verification as run in phase. |
| Caveats | Operator-facing UI for trips came in 3E+; 3D was API + schema + services. |

### 3E — Read-only trip list/detail UI (`3fac7d31`)

| Field | Detail |
|---|---|
| Commit | `3fac7d31` |
| Files | `apps/web/src/App.tsx`, `api.ts`, `TopNav.tsx`, `LoadWorkspacePage.tsx`, `TripWorkspacePage.tsx`, `TripsListPage.tsx`, `routes.ts` |
| Behavior | Routes `/trips` and `/trips/:id`; Trips in top nav; read-only trip list + detail shell; light Load workspace link surface. |
| Proof | `npm run build`; manual/HTTP checks as done in phase. |
| Caveats | Initial TripWorkspacePage was read-only; mutations added in 3G–3J. |

### Mirror cleanup — `active_trip_id` on loads (`4ca3f9ad`)

| Field | Detail |
|---|---|
| Commit | `4ca3f9ad` |
| Files | `app/schemas/load.py`, `app/services/loads.py`, selected tests |
| Behavior | `LoadResponse` / load read paths expose `active_trip_id`; write paths keep mirror in sync with trip membership rules on the backend. |
| Proof | Tests adjusted; build/deploy as per project norms. |
| Caveats | Mirror only; UI treats it as a hint for picker, not validation truth. |

### 3F — Create planned trip from load (`adee49b1`)

| Field | Detail |
|---|---|
| Commit | `adee49b1` |
| Files | `apps/web/src/api.ts` (`createPlannedTrip`), `LoadWorkspacePage.tsx` |
| Behavior | When load has `active_trip_id == null`, Create Planned Trip calls `POST /trips` with optional initial attach and navigates to `/trips/{id}`. |
| Proof | Build + manual/API paths as executed in phase. |
| Caveats | Gated on no `active_trip_id`; backend remains authoritative for conflicts. |

### 3G — Add load by ID (`4b554d5a`)

| Field | Detail |
|---|---|
| Commit | `4b554d5a` |
| Files | `api.ts` (`addLoadToTrip`), `TripWorkspacePage.tsx` |
| Behavior | Planned + not cancelled only: numeric Load ID + Add load; errors mapped for cancelled, duplicate, active on another trip, etc. |
| Proof | `npm run build`; HTTP/ASGI + nginx bundle checks in phase. |
| Caveats | Manual ID only until 3I. |

### 3H — Remove load from trip (`4d356230`)

| Field | Detail |
|---|---|
| Commit | `4d356230` |
| Files | `api.ts` (`removeLoadFromTrip`), `TripWorkspacePage.tsx` |
| Behavior | Remove on active member rows; confirm; soft-remove via API; active-only list filter where `removed_at == null`. |
| Proof | Build + authenticated proof for cancel/membership semantics. |
| Caveats | No historical member list in UI. |

### 3I — Search picker add (`84f752b1`)

| Field | Detail |
|---|---|
| Commit | `84f752b1` |
| Files | `TripWorkspacePage.tsx` only |
| Behavior | `listLoads({ search, page: 1, size: 20 })` + Search button; per-row Add; `active_trip_id` shown as hint only; manual Add by ID retained. |
| Proof | `npm run build`; ASGI + `GET /loads?search=...`; add/duplicate/other-trip/remove regression. |
| Caveats | Load list search semantics are backend-defined: load number, broker snapshot, reference, legacy `trip_number` on load row — not operational trip id. |

### 3J — Cancel planned trip (`397c0174`)

| Field | Detail |
|---|---|
| Commit | `397c0174` |
| Files | `api.ts` (`cancelTrip`), `TripWorkspacePage.tsx` |
| Behavior | Cancel Trip when `trip.status === "planned"` and `cancelled_at == null`; confirm; `POST /trips/{id}/cancel`; inline errors; empty-member copy when cancelled. |
| Proof | `reload_nginx_web.sh`; bundle contained `Cancel Trip`; ASGI cancel + DB + second cancel `409 TRIP_ALREADY_CANCELLED`; SPA route smoke. |
| Caveats | Cancelling a demo trip is destructive for that container; restores are manual by creating a new trip or re-adding loads. |

## 3. Current product behavior

- **Create planned trip from load:** `LoadWorkspacePage` shows Create Planned Trip when `active_trip_id` is null. It calls `POST /api/v1/trips` and opens `/trips/:id`. If the load is already on another active trip, the backend rejects; UI shows safe errors where wired.
- **View trip:** `TripsListPage` links to `/trips/:id`. Header shows trip number, status, `job_type`, and cancellation timestamp when present. Detail page shows equipment and active member loads.
- **Add by ID:** `TripWorkspacePage` allows numeric Load ID add only when trip is planned and `cancelled_at` is null.
- **Add by search picker:** Same gate as Add by ID. Search calls `GET /api/v1/loads?search=...`; each result can be added.
- **Remove load:** Same membership gate; confirms; soft-removes membership; backend updates `loads.active_trip_id`. `loads.status` is unchanged.
- **Cancel trip:** Same planned/open gate for Cancel; confirms container-only semantics; calls `POST /api/v1/trips/{id}/cancel`.
- **After cancel — member loads:** Backend sets `trip.status = cancelled`, sets `cancelled_at`, and soft-removes all active `trip_loads` rows. Detail still returns all `member_loads`, but the UI lists only active rows where `removed_at == null`, so the list looks empty and copy explains cancellation.
- **`loads.status`:** Not changed by cancel or remove-from-trip.
- **`loads.active_trip_id`:** Recomputed by backend from remaining active `trip_loads`; cleared when no active membership remains.

## 4. Backend/API contract

Prefix: `/api/v1/trips` — authenticated tenant JSON.

| Method | Path | Request | Response | Main errors / rules |
|---|---|---|---|---|
| GET | `/trips` | Query: `search`, `status`, `page`, `size` | `TripListPageResponse` with `{ items, page, size, total }`; items include `member_load_count`, `first_member` | Pagination is 1-based. |
| GET | `/trips/{id}` | none | `TripDetailResponse` with full trip + `member_loads` | `404 "Trip not found"` |
| POST | `/trips` | `CreatePlannedTripBody`: optional `status`, `job_type`, `driver_id`, `truck_id`, `trailer_id`, `load_ids[]` | `TripDetailResponse` with `201` | `400 INVALID_TRIP_STATUS` if requested status is cancelled; other validation, such as status/job_type length, may also use `400`. |
| POST | `/trips/{id}/loads` | `{ "load_id": number, "sequence_hint"?: number }` | `TripDetailResponse` | `404` load/trip; `409 TRIP_CANCELLED`, `DUPLICATE_TRIP_LOAD_MEMBERSHIP`, `LOAD_ACTIVE_ON_OTHER_TRIP` |
| POST | `/trips/{id}/loads/{load_id}/remove` | no body | `TripDetailResponse` | `404 TRIP_LOAD_NOT_FOUND`; `409 TRIP_CANCELLED` |
| POST | `/trips/{id}/cancel` | no body | `TripDetailResponse` | `404` trip; `409 TRIP_ALREADY_CANCELLED` |

Important rule: mutating handlers commit in the router after service calls. `TripDetailResponse` is the single detail contract for create/add/remove/cancel responses.

## 5. Architecture rules locked

- `trip_loads` rows with `removed_at IS NULL` are the source of truth for active trip membership.
- `loads.active_trip_id` is a convenience mirror derived by the backend from active `trip_loads`.
- UI must not repair mirror drift locally; show backend errors and optional hints only.
- Backend error codes and HTTP status are authoritative for conflicts and edge cases.
- Cancel planned trip does not cancel or delete commercial loads; it cancels the container and closes memberships.
- Remove load from trip does not change `loads.status`.
- Cancelled trips hide Add, search picker, Remove, and Cancel actions.

## 6. DB / migration state

Representative tenant Alembic artifacts in the trip slice:

- `e7f8a9b0c1d2_dispatch_trips_tenant_numbering` — tenant dispatch numbering / shared trip number pool.
- `x1a2b3c4d5e6_trips_trip_loads_foundation` — `trips` + `trip_loads` foundation.
- `y1a2b3c4d5e4_trip_mirror_catchup_missing_dispatch` — mirror catch-up for existing dispatch rows.
- `z3a4b5c6d7e8_trips_cancelled_at` — `trips.cancelled_at`.

Behavior:

- `trips.cancelled_at` is set on manual cancel, with `status = cancelled`.
- `trip_loads` membership ends through `removed_at` + `status_within_trip = removed`.
- `tenant_dispatch_numbering` / `mint_next_trip_number` is the shared trip number pool for planned containers and dispatch path integration.
- `legacy_dispatch_trip_id` on `TripDetailResponse` is a debug/internal link to `dispatch_trips`, not the primary product trip identifier.
- Dispatch board and `dispatch_trips` lifecycle are not replaced by this module.

## 7. UI files and routes

| Area | Location |
|---|---|
| Routes | `App.tsx`: `/trips` → `TripsListPage`, `/trips/:id` → `TripWorkspacePage` |
| Ops paths | `routes.ts`: `OPS.TRIPS`, `OPS.TRIP_DETAIL(id)` |
| Top nav | `TopNav.tsx`: Trips when path starts with `/trips` |
| List | `TripsListPage.tsx`: paginated trip directory; links to detail |
| Detail / lifecycle | `TripWorkspacePage.tsx`: equipment; member loads; search + Add by ID + Remove; Cancel Trip; errors; cancelled empty-state messaging |
| Create from load | `LoadWorkspacePage.tsx`: Create Planned Trip; View Trip link when `load.active_trip_id` is set |
| API | `api.ts`: `listTrips`, `getTrip`, `createPlannedTrip`, `addLoadToTrip`, `removeLoadFromTrip`, `cancelTrip`, `listLoads` |

## 8. Runtime proof summary

| Artifact | Role |
|---|---|
| Trip 78 | Cancelled reference, `T1E2173910072` |
| Trip 79 | Planned reference, `T1E2173910073`; member 523 in many proofs |
| Trip 81 | Planned then cancelled in 3J proof, `T1E2173910074`; member 526 |
| Load 518 | `TRIPCN-1184db10`; clean add/remove/search proof |
| Load 523 | On trip 79 in several scenarios |
| Load 526 | On trip 81; other-trip conflict when adding to 79; cancel 81 clears mirror for 526 |

Exact DB state may drift over time; proofs were against `tenant_demo` at runtime.

## 9. Known limitations / not done

- No dispatch board rewrite — operational board is still dispatch-centric; trips are additive.
- No custody / terminal / handoff UI or APIs in this slice.
- No trip execution statuses in the UI.
- No payroll / settlement integration with trip container.
- No historical member-load UI — only active rows in the main list; cancelled empty state is copy-only.
- No UI-side mirror repair — trust API + DB.
- Picker search is generic load search, not trip-aware filtering beyond what `listLoads` implements.
- Some phases relied on ASGI + DB or curl shell rather than full browser DOM proof.
- UI polish not implemented: `TripWorkspacePage` still shows `Trip container (read-only)`, which is stale after 3G–3J added Add by ID, search picker add, Remove load, and Cancel Trip. Do not change the string in product code unless separately approved. Recommended later: `Trip container` or `Operational trip workspace`.

## 10. Recommended next options

- **3K polish:** historical members on cancelled trips, clearer empty states, accessibility, analytics hooks, and optionally align the header label with operational reality.
- **Trip execution / custody report-first:** stops, handoff, in-transit semantics vs `trip_loads`.
- **Dispatch board trip-first redesign report-first:** align board read models with trips without breaking allocations.
- **Stash / unrelated work:** re-apply `stash@{0}` for theme/onboarding/brokers/infra/tests in small PRs after triage.
- **Ops / test PR:** repair trip mirror drift script, dual-write tests, certbot, seeds — separate from product 3K.

## 11. Acceptance checklist

- [x] Module 3D–3J + mirror accepted and described above.
- [x] Pushed — `origin/main` at `397c0174`.
- [x] Deployed where applicable — `reload_nginx_web.sh` run for 3J proof; nginx bakes `apps/web/dist`.
- [x] Working tree clean at module close.
- [x] 3K not started.

End of corrected module-close report.
