"""Idempotent backfill: create missing trips / trip_loads rows and align loads.active_trip_id to legacy mirrors.

Use when rows were added to dispatch_trips after Phase 1 but before Phase 2A live sync, leaving gaps.
Does not allocate new trip numbers, does not change dispatch_trips, loads.trip_number, or
loads.active_dispatch_trip_id (only sets active_trip_id to match the trips mirror when out of sync).

Safe to re-run: inserts are guarded with NOT EXISTS; update uses IS DISTINCT FROM.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Same semantics as x1a2b3c4d5e6 backfill and Phase 2A.
SQL_INSERT_TRIPS_FOR_MISSING_MIRRORS = """
INSERT INTO trips (
    tenant_id, trip_number, status, job_type, trailer_move_id,
    legacy_dispatch_trip_id, driver_id, truck_id, trailer_id,
    assigned_at, created_at, updated_at
)
SELECT
    dt.tenant_id,
    dt.trip_number,
    dt.status,
    dt.job_type,
    dt.trailer_move_id,
    dt.id,
    l.driver_id,
    l.truck_id,
    l.trailer_id,
    dt.assigned_at,
    dt.created_at,
    dt.updated_at
FROM dispatch_trips AS dt
LEFT JOIN loads AS l
    ON l.tenant_id = dt.tenant_id
    AND l.id = dt.load_id
WHERE NOT EXISTS (
    SELECT 1 FROM trips t WHERE t.legacy_dispatch_trip_id = dt.id
)
"""

SQL_INSERT_TRIP_LOADS_FOR_NEW_TRIPS = """
INSERT INTO trip_loads (
    tenant_id, trip_id, load_id, status_within_trip, sequence_hint,
    added_at, removed_at, created_at, updated_at
)
SELECT
    dt.tenant_id,
    t.id,
    dt.load_id,
    CASE WHEN dt.status = 'active' THEN 'active' ELSE 'removed' END,
    0,
    COALESCE(dt.assigned_at, dt.created_at, now()),
    CASE
        WHEN dt.status = 'active' THEN NULL
        ELSE COALESCE(dt.updated_at, now())
    END,
    now(),
    now()
FROM dispatch_trips AS dt
INNER JOIN trips AS t ON t.legacy_dispatch_trip_id = dt.id
WHERE dt.load_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM trip_loads AS tl
    WHERE tl.tenant_id = dt.tenant_id
      AND tl.trip_id = t.id
      AND tl.load_id = dt.load_id
  )
"""

SQL_UPDATE_LOADS_ACTIVE_TRIP_ID = """
UPDATE loads AS l
SET active_trip_id = t.id
FROM trips AS t
WHERE t.legacy_dispatch_trip_id = l.active_dispatch_trip_id
  AND l.active_dispatch_trip_id IS NOT NULL
  AND l.active_trip_id IS DISTINCT FROM t.id
"""


async def repair_missing_trip_mirrors(db: AsyncSession) -> dict[str, int]:
    """Idempotent: insert missing trip mirrors, then trip_loads, then fix loads.active_trip_id. Returns rowcounts (best effort)."""
    r1 = await db.execute(text(SQL_INSERT_TRIPS_FOR_MISSING_MIRRORS))
    n_trips = r1.rowcount or 0
    r2 = await db.execute(text(SQL_INSERT_TRIP_LOADS_FOR_NEW_TRIPS))
    n_trip_loads = r2.rowcount or 0
    r3 = await db.execute(text(SQL_UPDATE_LOADS_ACTIVE_TRIP_ID))
    n_loads = r3.rowcount or 0
    return {"trips_inserted": int(n_trips), "trip_loads_inserted": int(n_trip_loads), "loads_active_trip_id_updated": int(n_loads)}
