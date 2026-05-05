"""Test-only: put a load into legacy dispatched state without generic Load PATCH (Slice 1+).

Uses the same ensure_active_trip_for_freight_load path historical PATCH used, then sets status + mirrors.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.load import Load
from app.services import dispatch_trips as dispatch_trips_service


async def seed_load_dispatched_legacy_state(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    load_row = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
    if load_row is None:
        raise ValueError("load not found")
    dres = await dispatch_trips_service.ensure_active_trip_for_freight_load(db, tenant_id, load_id)
    load_row.status = "dispatched"
    load_row.active_dispatch_trip_id = dres.dispatch_trip.id
    load_row.trip_number = dres.dispatch_trip.trip_number
    load_row.active_trip_id = dres.container_trip_id
    load_row.concurrency_version = int(load_row.concurrency_version) + 1
    await db.commit()
