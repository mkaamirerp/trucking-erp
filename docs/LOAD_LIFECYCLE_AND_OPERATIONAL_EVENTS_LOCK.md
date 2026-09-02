# TruckERP — Load Lifecycle & Operational Events

**Status:** **SUPERSEDED — historical pointer only.**

**Superseded by:** [`trip-foundation.md`](./trip-foundation.md), [`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`](./DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md), and [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](./TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md).

This file previously described `Assigned`, `Dispatched`, `In Transit`, `Delivered`, and `Closed` as a single Load lifecycle. That model conflicts with the current Trip-first architecture and must not be used for new code or UI.

## Current boundary

- **Load** = commercial/readiness/revenue truth.
- **Trip** = operational/payable movement truth.
- **TripLoad** = membership between a Load and a Trip.
- **Custody/Audit** = physical continuity and handoff history.
- **Dispatch Load** = an operator action involving an existing Load and a Trip; it is **not** a separate entity, table, or lifecycle.

## Current status ownership

- Target Load commercial/readiness states are `draft`, `ready`, and future explicit commercial `cancelled`.
- Current shipped Trip lifecycle is `planned -> assigned -> in_progress -> completed`, plus `cancelled`.
- Legacy Load values such as `assigned`, `dispatched`, `in_transit`, and `delivered` remain read/compatibility vocabulary only. They must not become new operational writes.
- Pickup, delivery, rejection, yard return, reassignment, handoff, and trailer transfer belong to Trip execution and/or custody events—not a Load execution ladder.

## Durable rules retained from the historical note

- A commercial Load persists across Trips until commercial completion.
- A Trip may carry multiple Loads, and one Load may move through multiple Trips.
- Do not duplicate a commercial Load merely because responsibility moves to another Trip.
- Custody must remain visible and auditable; no handoff may silently disappear.
- Trip completion does not by itself mean the commercial Load reached its final receiver.

Use the superseding documents above for implementation details and precedence.
