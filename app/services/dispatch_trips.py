"""Canonical dispatch trip allocation and lifecycle (tenant DB)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.trip_dispatch import (
    DEFAULT_NEXT_TRIP_NUMERIC,
    DISPATCH_RESOURCES_REQUIRED,
    DISPATCH_TRIP_STATUS_ACTIVE,
    DISPATCH_TRIP_STATUS_CANCELLED,
    JOB_TYPE_FREIGHT_LOAD,
    TRIP_NUMERIC_WIDTH,
    TRIP_NUMBER_PREFIX_MAX_LEN,
    TRIP_NUMBER_PREFIX_MIN_LEN,
    TRIP_NUMBER_PREFIX_NOT_CONFIGURED,
)
from app.models.dispatch_trip import DispatchTrip, TenantDispatchNumbering
from app.models.load import Load


_PREFIX_RE = re.compile(r"^[A-Z0-9]+$")


def normalize_and_validate_trip_prefix(raw: str) -> str:
    p = (raw or "").strip().upper()
    if len(p) < TRIP_NUMBER_PREFIX_MIN_LEN or len(p) > TRIP_NUMBER_PREFIX_MAX_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": f"trip_number_prefix must be {TRIP_NUMBER_PREFIX_MIN_LEN}-{TRIP_NUMBER_PREFIX_MAX_LEN} alphanumeric characters",
                "code": "INVALID_TRIP_NUMBER_PREFIX",
            },
        )
    if not _PREFIX_RE.match(p):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "trip_number_prefix must be A-Z or digits only", "code": "INVALID_TRIP_NUMBER_PREFIX"},
        )
    return p


def numbering_config_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "detail": "Trip number prefix is not configured or locked. Set it in Admin → dispatch numbering.",
            "code": TRIP_NUMBER_PREFIX_NOT_CONFIGURED,
        },
    )


async def get_or_create_numbering_for_update(
    db: AsyncSession, tenant_id: int
) -> TenantDispatchNumbering | None:
    result = await db.execute(
        select(TenantDispatchNumbering).where(TenantDispatchNumbering.tenant_id == tenant_id).with_for_update()
    )
    row = result.scalar_one_or_none()
    return row


async def lock_trip_prefix(db: AsyncSession, tenant_id: int, prefix: str) -> TenantDispatchNumbering:
    """Set and lock prefix (one-time). Creates numbering row if needed."""
    normalized = normalize_and_validate_trip_prefix(prefix)
    row = await get_or_create_numbering_for_update(db, tenant_id)
    if row and row.prefix_locked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Trip number prefix is already locked", "code": "TRIP_PREFIX_ALREADY_LOCKED"},
        )
    if row is None:
        row = TenantDispatchNumbering(
            tenant_id=tenant_id,
            trip_number_prefix=normalized,
            prefix_locked_at=datetime.now(timezone.utc),
            next_numeric=DEFAULT_NEXT_TRIP_NUMERIC,
        )
        db.add(row)
    else:
        row.trip_number_prefix = normalized
        row.prefix_locked_at = datetime.now(timezone.utc)
        if row.next_numeric is None or row.next_numeric < DEFAULT_NEXT_TRIP_NUMERIC:
            row.next_numeric = DEFAULT_NEXT_TRIP_NUMERIC
    await db.flush()
    return row


async def get_numbering_public(db: AsyncSession, tenant_id: int) -> TenantDispatchNumbering | None:
    return await db.scalar(select(TenantDispatchNumbering).where(TenantDispatchNumbering.tenant_id == tenant_id))


async def get_active_trip_for_load(db: AsyncSession, tenant_id: int, load_id: int) -> DispatchTrip | None:
    return await db.scalar(
        select(DispatchTrip).where(
            DispatchTrip.tenant_id == tenant_id,
            DispatchTrip.load_id == load_id,
            DispatchTrip.status == DISPATCH_TRIP_STATUS_ACTIVE,
        )
    )


async def ensure_active_trip_for_freight_load(db: AsyncSession, tenant_id: int, load: Load) -> DispatchTrip:
    """Mint trip on first dispatched; idempotent if active trip exists. Syncs load read-model fields."""
    existing = await get_active_trip_for_load(db, tenant_id, load.id)
    if existing is not None:
        await _sync_load_read_model(db, load, existing)
        return existing

    row = await get_or_create_numbering_for_update(db, tenant_id)
    if row is None or row.prefix_locked_at is None or not (row.trip_number_prefix or "").strip():
        raise numbering_config_error()

    n = int(row.next_numeric)
    trip_number = f"{row.trip_number_prefix}{n:0{TRIP_NUMERIC_WIDTH}d}"
    row.next_numeric = n + 1

    trip = DispatchTrip(
        tenant_id=tenant_id,
        trip_number=trip_number,
        job_type=JOB_TYPE_FREIGHT_LOAD,
        status=DISPATCH_TRIP_STATUS_ACTIVE,
        load_id=load.id,
        trailer_move_id=None,
    )
    db.add(trip)
    await db.flush()
    await _sync_load_read_model(db, load, trip)
    return trip


async def _sync_load_read_model(db: AsyncSession, load: Load, trip: DispatchTrip | None) -> None:
    if trip is not None and trip.status == DISPATCH_TRIP_STATUS_ACTIVE:
        load.active_dispatch_trip_id = trip.id
        load.trip_number = trip.trip_number
    else:
        load.active_dispatch_trip_id = None
        load.trip_number = None


async def cancel_active_trip_for_load(db: AsyncSession, tenant_id: int, load_id: int, load: Load | None = None) -> None:
    trip = await get_active_trip_for_load(db, tenant_id, load_id)
    if trip is None:
        if load is not None:
            load.active_dispatch_trip_id = None
            load.trip_number = None
        return
    trip.status = DISPATCH_TRIP_STATUS_CANCELLED
    if load is not None:
        await _sync_load_read_model(db, load, None)
