# MANDATORY READ-FIRST — BEFORE ANY PHASE 3D / TRIP ACTION WORK

**Do not start implementation from memory.**  
**Do not infer architecture from current Load page behavior alone.**  
The docs below define the target architecture; **current code is transitional**.

Before planning or implementing **planned Trip creation**, **add/remove Load**, **Trip cancel**, or **assignment** logic, read these materials **fully**, in order.

---

## 1. Authoritative operational lock

**[`trip-foundation.md`](trip-foundation.md)**  

This is the authoritative Trip / Load / TripLoad operational rules lock. It supersedes earlier snapshots where they differ.

---

## 2. Core architecture narrative

**[`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](TRIP_CONTAINER_VS_LOAD_FOUNDATION.md)**  

Explains the core architecture:

- Trip = operational execution container  
- Load = commercial/broker contract  
- `LoadWorkspacePage` stays but becomes preparation/commercial confirmation  
- `TripWorkspacePage` becomes operational root  
- Do not build “Load page v2” with trip toggles  

---

## 3. Schema direction

**[`TRIP_FIRST_DDL_CONTRACT.md`](TRIP_FIRST_DDL_CONTRACT.md)**  

Defines schema direction:

- `trips`  
- `trip_loads`  
- `loads` as commercial truth  
- `load_stops` as contractual stop truth  
- future `trip_events` / `trip_stops` / `load_custody_events` compatibility  

---

## 4. Lifecycle and future compatibility

**[`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md)**  

Read for **future** compatibility (do **not** implement all of this now, but **do not** design **against** it):

- yard/terminal  
- custody  
- handoff  
- city pickup to yard  
- load continuing across multiple trips  
- trailer transfer  

---

## 5. Trip number rule (legacy vs planned Trip)

**[`DISPATCH_TRIP_NUMBER_RULE.md`](DISPATCH_TRIP_NUMBER_RULE.md)**  

Read carefully: the **old** rule may conflict with the **new** planned-trip rule. Target direction (see also `trip-foundation.md`):

- trip number can be minted when the Trip container is created/planned  
- trip number is never reused  
- cancelled/empty Trip remains for audit  

---

## 6. Current numbering implementation

**[`DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`](DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md)**  

Understand current allocator/numbering implementation so existing trip number behavior is not broken unintentionally.

---

## 7. Phase 1 foundation already in place

**[`PHASE1_TRIP_FOUNDATION_PLAN.md`](PHASE1_TRIP_FOUNDATION_PLAN.md)**  

Understand what Phase 1 already established:

- `trips` / `trip_loads` schema  
- backfill  
- mirror-only warning  
- `dispatch_trips` as transition bridge  

---

## 8. Pointer to operational rules filename

**[`TRIP_CONTAINER_OPERATIONAL_RULES.md`](TRIP_CONTAINER_OPERATIONAL_RULES.md)** — thin pointer; authoritative body remains `trip-foundation.md`.

---

## 9. Code to inspect **after** the docs

Paths are relative to repo root:

| Area | Path |
|------|------|
| Models | `app/models/trip.py`, `app/models/dispatch_trip.py`, `app/models/load.py` |
| Services | `app/services/trips.py`, `app/services/dispatch_trips.py`, `app/services/loads.py` |
| API | `app/routers/trips.py` |
| Schemas | `app/schemas/trip_read.py`, `app/schemas/load.py` |
| Tests | `tests/test_trip_foundation.py`, `tests/test_trip_container_dual_write.py`, `tests/test_trip_read_detail.py` |

---

## Summary

| Do | Don’t |
|----|--------|
| Read all listed docs end-to-end first | Rely on memory or old snapshots |
| Treat `trip-foundation.md` as the lock | Assume Load page behavior defines target architecture |
| Respect Phase 1 bridge and numbering docs | Change trip numbering without reading implementation plan |
