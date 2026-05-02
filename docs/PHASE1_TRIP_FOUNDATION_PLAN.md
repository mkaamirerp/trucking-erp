# Phase 1 — Trip container schema foundation (plan & acceptance)

**Report date:** 2026-04-27

## Five pillars (unchanged; Phase 1 supports 1 & 2 only)

1. **Establish the Trip container foundation** — This slice adds the `trips` table and ORM, populated by **historical** backfill from `dispatch_trips`, not by live dispatches.
2. **Define Load membership in the container** — This slice adds `trip_loads` and backfills it for existing freight `dispatch_trips` rows. **Not** a live join API yet.
3. **LoadWorkspacePage = load prep / commercial** — No UI or writer changes; load editing stays on existing paths.
4. **Operational assignment on Trip later** — Explicitly **not** in Phase 1.
5. **Full Trip page / board later** — Explicitly **not** in Phase 1.

## Live-sync warning (mandatory)

**Phase 1 `trips` / `trip_loads` / `loads.active_trip_id` are schema + historical backfill mirror only.** The **current** live dispatch writer remains `ensure_active_trip_for_freight_load` → `dispatch_trips`, and the load read-model **remains** `loads.active_dispatch_trip_id` and `loads.trip_number`.

- **New** dispatches after this migration still create only `dispatch_trips` and still update `loads.active_dispatch_trip_id` and `loads.trip_number` — they **do not** create `trips` or `trip_loads` rows and **do not** set `loads.active_trip_id`.
- **Do not** use `trips` / `trip_loads` (or `loads.active_trip_id` alone) as **live operational read authority** until **Phase 2** dual-write / service flip. Until then, treat them as backfilled + future-ready, not the source of truth for “what is running now.”
- This slice does **not** change the live writer in `app/services/dispatch_trips.py` or `app/services/loads.py`.

### Product lock after Phase 1 (docs only — 2026)

**Does not retroactively change Phase 1 scope.** Subsequent work ([`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md), [`PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md`](./PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md)) locks: **trip number mint on planned `trips` create**, **zero-load planned trips**, **Load vs Trip cancellation separation**, and **allocator extension to `trips`**. Implementing that requires **later phases** (dual-write / service flip)—not reinterpretation of Phase 1 as having already done it.

## Scope

- **In:** New tables, migration + backfill, ORM, schema guards (reject client `active_trip_id`), tests, comments.
- **Out:** Frontend, TripWorkspace, board pivot, parser/Lab, `CREATE INDEX CONCURRENTLY`, any prod `DROP` cleanup in the migration file.

**Implementation:** `alembic_tenant/versions/x1a2b3c4d5e6_trips_trip_loads_foundation.py`, `app/models/trip.py`, `tests/test_trip_foundation.py`, related `load` / schema / `__init__` / `dispatch_trip` comment.

## Option B (this slice)

- New proper `trips` + `trip_loads` tables; `dispatch_trips` remains the **live** trip-number/allocator bridge until Phase 2.
- No second allocator; no behavior change to allocation timing or dispatch flow in application code.

## Downgrade (best-effort)

`downgrade()` in the migration: drops `fk_loads_active_trip`, `loads` indexes and `active_trip_id` column, then all `trip_loads` indexes and `trip_loads` table, then all `trips` indexes and `trips` table. It does **not** modify `dispatch_trips`, `loads.trip_number`, or `loads.active_dispatch_trip_id`.

## Transaction & safety (see migration header for detail)

- No `CONCURRENTLY` index builds; the revision’s `upgrade()` runs in Alembic’s **single** transaction. On error before commit, expect a **full** rollback of this revision’s DDL and data changes (standard PostgreSQL + Alembic online mode).
- **Prod path:** from a **clean** pre-upgrade state, run a normal `upgrade head` once. Do not embed dev-only `DROP TABLE` in the migration.
