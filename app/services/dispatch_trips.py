"""Canonical dispatch trip allocation and lifecycle (tenant DB)."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
from app.models.trip import Trip, TripLoad


# Matches Phase 1 backfill: trip_loads.status_within_trip for active membership vs soft-removed.
TRIP_LOAD_STATUS_WITHIN_ACTIVE = "active"
TRIP_LOAD_STATUS_WITHIN_REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class FreightActiveDispatchResult:
    """Result of `ensure_active_trip_for_freight_load` after `dispatch_trips` + container mirror are aligned."""

    dispatch_trip: DispatchTrip
    container_trip_id: int


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


async def mint_next_trip_number(db: AsyncSession, tenant_id: int) -> str:
    """Acquire tenant_dispatch_numbering row lock, increment sequence, return new full trip_number.

    Single shared pool for all Trip containers (planned trips and legacy dispatch_trips paths).
    Caller runs inside a DB transaction.
    """
    row = await get_or_create_numbering_for_update(db, tenant_id)
    if row is None or row.prefix_locked_at is None or not (row.trip_number_prefix or "").strip():
        raise numbering_config_error()
    n = int(row.next_numeric)
    trip_number = f"{row.trip_number_prefix}{n:0{TRIP_NUMERIC_WIDTH}d}"
    row.next_numeric = n + 1
    return trip_number


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


async def _upsert_trip_and_membership(
    db: AsyncSession, tenant_id: int, load_id: int, d_trip: DispatchTrip, load: Load
) -> int:
    """Create or update `trips` + ensure one active `trip_loads` row for this freight dispatch. Returns trips.id."""
    container = await db.scalar(
        select(Trip).where(
            Trip.tenant_id == tenant_id,
            Trip.legacy_dispatch_trip_id == d_trip.id,
        )
    )
    now = datetime.now(timezone.utc)
    if container is None:
        container = Trip(
            tenant_id=tenant_id,
            trip_number=d_trip.trip_number,
            status=d_trip.status,
            job_type=d_trip.job_type,
            trailer_move_id=d_trip.trailer_move_id,
            legacy_dispatch_trip_id=d_trip.id,
            driver_id=load.driver_id,
            truck_id=load.truck_id,
            trailer_id=load.trailer_id,
            assigned_at=d_trip.assigned_at,
            created_at=d_trip.created_at,
            updated_at=d_trip.updated_at,
        )
        db.add(container)
        await db.flush()
    else:
        container.trip_number = d_trip.trip_number
        container.status = d_trip.status
        container.job_type = d_trip.job_type
        container.trailer_move_id = d_trip.trailer_move_id
        container.driver_id = load.driver_id
        container.truck_id = load.truck_id
        container.trailer_id = load.trailer_id
        container.updated_at = now

    active_tl = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.trip_id == container.id,
            TripLoad.load_id == load_id,
            TripLoad.removed_at.is_(None),
        )
    )
    if active_tl is None:
        add_ref = d_trip.assigned_at or d_trip.created_at
        db.add(
            TripLoad(
                tenant_id=tenant_id,
                trip_id=container.id,
                load_id=load_id,
                status_within_trip=TRIP_LOAD_STATUS_WITHIN_ACTIVE,
                sequence_hint=0,
                added_at=add_ref,
                removed_at=None,
            )
        )
        await db.flush()

    return int(container.id)


async def ensure_active_trip_for_freight_load(
    db: AsyncSession, tenant_id: int, load_id: int
) -> FreightActiveDispatchResult:
    """Mint dispatch_trip on first dispatched; idempotent. Mirrors `trips` + `trip_loads` for Phase 2A.

    Does not mutate the Load ORM row — caller applies active_dispatch_trip_id, trip_number, active_trip_id
    via CAS UPDATE.
    """
    existing = await get_active_trip_for_load(db, tenant_id, load_id)
    if existing is not None:
        d_trip = existing
    else:
        trip_number = await mint_next_trip_number(db, tenant_id)

        d_trip = DispatchTrip(
            tenant_id=tenant_id,
            trip_number=trip_number,
            job_type=JOB_TYPE_FREIGHT_LOAD,
            status=DISPATCH_TRIP_STATUS_ACTIVE,
            load_id=load_id,
            trailer_move_id=None,
        )
        db.add(d_trip)
        await db.flush()

    load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
    if load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    container_trip_id = await _upsert_trip_and_membership(db, tenant_id, load_id, d_trip, load)
    return FreightActiveDispatchResult(dispatch_trip=d_trip, container_trip_id=container_trip_id)


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

    now = datetime.now(timezone.utc)
    mirror = await db.scalar(
        select(Trip).where(
            Trip.tenant_id == tenant_id,
            Trip.legacy_dispatch_trip_id == trip.id,
        )
    )
    if mirror is not None:
        mirror.status = DISPATCH_TRIP_STATUS_CANCELLED
        mirror.updated_at = now
        active_tl = await db.scalar(
            select(TripLoad).where(
                TripLoad.tenant_id == tenant_id,
                TripLoad.trip_id == mirror.id,
                TripLoad.load_id == load_id,
                TripLoad.removed_at.is_(None),
            )
        )
        if active_tl is not None:
            active_tl.status_within_trip = TRIP_LOAD_STATUS_WITHIN_REMOVED
            active_tl.removed_at = now

    if load is not None:
        await _sync_load_read_model(db, load, None)
