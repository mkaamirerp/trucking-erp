"""Trip container reads (Phase 3A). Membership is always from trip_loads — not loads.active_trip_id."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.trip_dispatch import (
    JOB_TYPE_FREIGHT_LOAD,
    TRIP_CONTAINER_STATUS_CANCELLED,
    TRIP_CONTAINER_STATUS_PLANNED,
    TRIP_LOAD_STATUS_WITHIN_PLANNED,
)
from app.models.driver import Driver
from app.models.load import Load, LoadStop
from app.models.trip import Trip, TripLoad
from app.models.trailer import Trailer
from app.models.truck import Truck
from app.schemas.load import NestedDriver, NestedTrailer, NestedTruck
from app.schemas.trip_read import (
    TripDetailResponse,
    TripFirstMemberSummary,
    TripListItemResponse,
    TripMemberLoadSummary,
)
from app.utils.pagination import paginate
from app.services.dispatch_trips import TRIP_LOAD_STATUS_WITHIN_REMOVED, mint_next_trip_number


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return float(v)


def _one_stop_line(st: LoadStop) -> str:
    city = (st.city or "").strip()
    stp = (st.state_or_province or "").strip()
    if city and stp:
        return f"{city}, {stp}"
    if city:
        return city
    if st.facility_name and str(st.facility_name).strip():
        return str(st.facility_name).strip()[:80]
    return "—"


async def _stop_route_summary_map(
    db: AsyncSession, tenant_id: int, load_ids: list[int]
) -> dict[int, str]:
    if not load_ids:
        return {}
    res = await db.execute(
        select(LoadStop)
        .where(
            LoadStop.tenant_id == tenant_id,
            LoadStop.load_id.in_(load_ids),
        )
        .order_by(LoadStop.load_id, LoadStop.sequence)
    )
    by_load: dict[int, list[LoadStop]] = {}
    for row in res.scalars():
        st = row
        by_load.setdefault(st.load_id, []).append(st)
    out: dict[int, str] = {}
    for lid, stops in by_load.items():
        parts: list[str] = []
        for s in stops:
            line = _one_stop_line(s)
            if line != "—":
                parts.append(line)
        if parts:
            out[lid] = " → ".join(parts)
    return out


def _nd_from_driver(d: Driver) -> NestedDriver:
    return NestedDriver.model_validate(
        {
            "id": d.id,
            "first_name": d.first_name,
            "last_name": d.last_name,
            "phone": d.phone,
            "email": d.email,
        }
    )


async def list_trips(
    db: AsyncSession,
    tenant_id: int,
    *,
    search: str | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 25,
) -> dict[str, Any]:
    """List trips: member_load_count and first_member are derived from trip_loads (active rows only), not loads.active_trip_id."""
    stmt = select(Trip).where(Trip.tenant_id == tenant_id)
    st = (status or "").strip()
    if st:
        stmt = stmt.where(Trip.status == st)
    q = (search or "").strip()
    if q:
        pat = f"%{q}%"
        load_match = (
            select(TripLoad.trip_id)
            .join(
                Load,
                and_(TripLoad.tenant_id == Load.tenant_id, TripLoad.load_id == Load.id),
            )
            .where(
                TripLoad.tenant_id == tenant_id,
                or_(
                    Load.load_number.ilike(pat),
                    Load.broker_name_snapshot.ilike(pat),
                    Load.broker_load_reference.ilike(pat),
                ),
            )
            .distinct()
        )
        stmt = stmt.where(or_(Trip.trip_number.ilike(pat), Trip.id.in_(load_match)))

    stmt = stmt.order_by(Trip.id.desc())
    paged = await paginate(db, stmt, page=page, size=size)
    trips: list[Trip] = paged["items"]
    tids = [int(t.id) for t in trips]
    if not tids:
        return {"items": [], "page": paged["page"], "size": paged["size"], "total": paged["total"]}

    cnt_rows = await db.execute(
        select(TripLoad.trip_id, func.count().label("cnt"))
        .where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.trip_id.in_(tids),
            TripLoad.removed_at.is_(None),
        )
        .group_by(TripLoad.trip_id)
    )
    count_map: dict[int, int] = {int(r[0]): int(r[1]) for r in cnt_rows.all()}

    mrows = (
        await db.execute(
            select(TripLoad, Load)
            .join(
                Load,
                and_(TripLoad.tenant_id == Load.tenant_id, TripLoad.load_id == Load.id),
            )
            .where(
                TripLoad.tenant_id == tenant_id,
                TripLoad.trip_id.in_(tids),
                TripLoad.removed_at.is_(None),
            )
        )
    ).all()

    by_trip: dict[int, list[tuple[TripLoad, Load]]] = {}
    for tl, lo in mrows:
        by_trip.setdefault(int(tl.trip_id), []).append((tl, lo))
    first_by_trip: dict[int, tuple[TripLoad, Load]] = {}
    for tid, pairs in by_trip.items():
        pairs.sort(
            key=lambda p: (p[0].sequence_hint is None, p[0].sequence_hint or 0, p[0].added_at),
        )
        first_by_trip[tid] = pairs[0]

    first_load_ids = [int(lo.id) for _, lo in first_by_trip.values()]
    route_by = await _stop_route_summary_map(db, tenant_id, first_load_ids)

    driver_ids = {t.driver_id for t in trips if t.driver_id is not None}
    truck_ids = {t.truck_id for t in trips if t.truck_id is not None}
    trailer_ids = {t.trailer_id for t in trips if t.trailer_id is not None}
    dr_map: dict[int, Driver] = {}
    if driver_ids:
        res = await db.execute(
            select(Driver).where(Driver.tenant_id == tenant_id, Driver.id.in_(driver_ids))
        )
        for d in res.scalars():
            dr_map[int(d.id)] = d
    tk_map: dict[int, Truck] = {}
    if truck_ids:
        res = await db.execute(select(Truck).where(Truck.tenant_id == tenant_id, Truck.id.in_(truck_ids)))
        for t in res.scalars():
            tk_map[int(t.id)] = t
    trr_map: dict[int, Trailer] = {}
    if trailer_ids:
        res = await db.execute(select(Trailer).where(Trailer.tenant_id == tenant_id, Trailer.id.in_(trailer_ids)))
        for t in res.scalars():
            trr_map[int(t.id)] = t

    items: list[TripListItemResponse] = []
    for tr in trips:
        tid = int(tr.id)
        d_obj = dr_map.get(tr.driver_id) if tr.driver_id is not None else None
        nd = _nd_from_driver(d_obj) if d_obj else None
        t_obj = tk_map.get(tr.truck_id) if tr.truck_id is not None else None
        nt = NestedTruck.model_validate(t_obj) if t_obj else None
        r_obj = trr_map.get(tr.trailer_id) if tr.trailer_id is not None else None
        ntr = NestedTrailer.model_validate(r_obj) if r_obj else None

        fm: TripFirstMemberSummary | None = None
        if tid in first_by_trip:
            _, lo = first_by_trip[tid]
            lid = int(lo.id)
            fm = TripFirstMemberSummary(
                load_number=lo.load_number,
                broker_name_snapshot=lo.broker_name_snapshot,
                broker_load_reference=lo.broker_load_reference,
                stop_route_summary=route_by.get(lid),
            )

        items.append(
            TripListItemResponse(
                id=tid,
                trip_number=tr.trip_number,
                status=tr.status,
                job_type=tr.job_type,
                driver_id=tr.driver_id,
                driver=nd,
                truck_id=tr.truck_id,
                truck=nt,
                trailer_id=tr.trailer_id,
                trailer=ntr,
                assigned_at=tr.assigned_at,
                cancelled_at=tr.cancelled_at,
                created_at=tr.created_at,
                updated_at=tr.updated_at,
                member_load_count=count_map.get(tid, 0),
                first_member=fm,
            )
        )

    return {"items": items, "page": paged["page"], "size": paged["size"], "total": paged["total"]}


async def get_trip_detail(db: AsyncSession, tenant_id: int, trip_id: int) -> TripDetailResponse | None:
    tr = await db.get(Trip, trip_id)
    if tr is None or tr.tenant_id != tenant_id:
        return None

    members_stmt: Select[tuple[TripLoad, Load]] = (
        select(TripLoad, Load)
        .join(
            Load,
            and_(TripLoad.tenant_id == Load.tenant_id, TripLoad.load_id == Load.id),
        )
        .where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.trip_id == trip_id,
        )
        .order_by(TripLoad.added_at)
    )
    mrows = (await db.execute(members_stmt)).all()

    load_ids = [int(row[1].id) for row in mrows]
    route_by_load = await _stop_route_summary_map(db, tenant_id, load_ids)

    member_loads: list[TripMemberLoadSummary] = []
    for tl, lo in mrows:
        lo_id = int(lo.id)
        member_loads.append(
            TripMemberLoadSummary(
                trip_load_id=int(tl.id),
                load_id=lo_id,
                status_within_trip=tl.status_within_trip,
                sequence_hint=tl.sequence_hint,
                added_at=tl.added_at,
                removed_at=tl.removed_at,
                load_number=lo.load_number,
                broker_name_snapshot=lo.broker_name_snapshot,
                broker_load_reference=lo.broker_load_reference,
                commodity=lo.commodity,
                rate=_num(lo.rate),
                customer_rate=_num(lo.customer_rate),
                stop_route_summary=route_by_load.get(lo_id),
            )
        )
    # Optional: re-order by sequence_hint (nulls last) then added_at
    member_loads.sort(
        key=lambda m: (m.sequence_hint is None, m.sequence_hint or 0, m.added_at),
    )

    driver: Driver | None = None
    if tr.driver_id is not None:
        driver = await db.get(Driver, tr.driver_id)
        if driver and driver.tenant_id != tenant_id:
            driver = None
    truck: Truck | None = None
    if tr.truck_id is not None:
        truck = await db.get(Truck, tr.truck_id)
        if truck and truck.tenant_id != tenant_id:
            truck = None
    trailer: Trailer | None = None
    if tr.trailer_id is not None:
        trailer = await db.get(Trailer, tr.trailer_id)
        if trailer and trailer.tenant_id != tenant_id:
            trailer = None

    nd = _nd_from_driver(driver) if driver else None
    nt = NestedTruck.model_validate(truck) if truck else None
    ntr = NestedTrailer.model_validate(trailer) if trailer else None

    return TripDetailResponse(
        id=int(tr.id),
        tenant_id=int(tr.tenant_id),
        trip_number=tr.trip_number,
        status=tr.status,
        job_type=tr.job_type,
        driver_id=tr.driver_id,
        driver=nd,
        truck_id=tr.truck_id,
        truck=nt,
        trailer_id=tr.trailer_id,
        trailer=ntr,
        assigned_at=tr.assigned_at,
        cancelled_at=tr.cancelled_at,
        created_at=tr.created_at,
        updated_at=tr.updated_at,
        legacy_dispatch_trip_id=tr.legacy_dispatch_trip_id,
        member_loads=member_loads,
    )


async def _validate_assignment_targets(
    db: AsyncSession,
    tenant_id: int,
    *,
    driver_id: int | None,
    truck_id: int | None,
    trailer_id: int | None,
) -> None:
    if driver_id is not None:
        d = await db.get(Driver, driver_id)
        if d is None or d.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")
    if truck_id is not None:
        t = await db.get(Truck, truck_id)
        if t is None or t.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck not found")
    if trailer_id is not None:
        r = await db.get(Trailer, trailer_id)
        if r is None or r.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trailer not found")


async def _sync_load_active_trip_pointer(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    """Set loads.active_trip_id from remaining active trip_loads rows (convenience only)."""
    load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
    if load is None:
        return
    other = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.load_id == load_id,
            TripLoad.removed_at.is_(None),
        )
    )
    if other is not None:
        load.active_trip_id = int(other.trip_id)
    else:
        load.active_trip_id = None


async def _insert_trip_load_row(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    *,
    sequence_hint: int | None,
    status_within: str = TRIP_LOAD_STATUS_WITHIN_PLANNED,
) -> None:
    trip = await db.get(Trip, trip_id)
    if trip is None or trip.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.status == TRIP_CONTAINER_STATUS_CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Trip is cancelled", "code": "TRIP_CANCELLED"},
        )

    load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
    if load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    same = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.trip_id == trip_id,
            TripLoad.load_id == load_id,
            TripLoad.removed_at.is_(None),
        )
    )
    if same is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Load already on this trip", "code": "DUPLICATE_TRIP_LOAD_MEMBERSHIP"},
        )

    other_trip = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.load_id == load_id,
            TripLoad.removed_at.is_(None),
            TripLoad.trip_id != trip_id,
        )
    )
    if other_trip is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Load already active on another trip", "code": "LOAD_ACTIVE_ON_OTHER_TRIP"},
        )

    now = datetime.now(timezone.utc)
    db.add(
        TripLoad(
            tenant_id=tenant_id,
            trip_id=trip_id,
            load_id=load_id,
            status_within_trip=status_within,
            sequence_hint=sequence_hint,
            added_at=now,
            removed_at=None,
        )
    )
    await db.flush()

    if load.active_trip_id is None:
        load.active_trip_id = trip_id


async def create_planned_trip(
    db: AsyncSession,
    tenant_id: int,
    *,
    status: str | None = None,
    job_type: str | None = None,
    driver_id: int | None = None,
    truck_id: int | None = None,
    trailer_id: int | None = None,
    load_ids: list[int] | None = None,
) -> TripDetailResponse:
    st = (status or TRIP_CONTAINER_STATUS_PLANNED).strip() or TRIP_CONTAINER_STATUS_PLANNED
    if st == TRIP_CONTAINER_STATUS_CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Cannot create a trip in cancelled status", "code": "INVALID_TRIP_STATUS"},
        )
    jt = (job_type or JOB_TYPE_FREIGHT_LOAD).strip() or JOB_TYPE_FREIGHT_LOAD
    if len(jt) > 32 or len(st) > 32:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status/job_type too long")

    await _validate_assignment_targets(db, tenant_id, driver_id=driver_id, truck_id=truck_id, trailer_id=trailer_id)

    trip_number = await mint_next_trip_number(db, tenant_id)
    trip = Trip(
        tenant_id=tenant_id,
        trip_number=trip_number,
        status=st,
        job_type=jt,
        trailer_move_id=None,
        legacy_dispatch_trip_id=None,
        driver_id=driver_id,
        truck_id=truck_id,
        trailer_id=trailer_id,
        assigned_at=None,
        cancelled_at=None,
    )
    db.add(trip)
    await db.flush()

    for lid in load_ids or []:
        await _insert_trip_load_row(db, tenant_id, int(trip.id), int(lid), sequence_hint=None)

    detail = await get_trip_detail(db, tenant_id, int(trip.id))
    assert detail is not None
    return detail


async def add_load_to_trip(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    *,
    sequence_hint: int | None = None,
) -> TripDetailResponse:
    await _insert_trip_load_row(db, tenant_id, trip_id, load_id, sequence_hint=sequence_hint)
    detail = await get_trip_detail(db, tenant_id, trip_id)
    assert detail is not None
    return detail


async def remove_load_from_trip(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
) -> TripDetailResponse:
    trip = await db.get(Trip, trip_id)
    if trip is None or trip.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.status == TRIP_CONTAINER_STATUS_CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Trip is cancelled", "code": "TRIP_CANCELLED"},
        )

    tl = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.trip_id == trip_id,
            TripLoad.load_id == load_id,
            TripLoad.removed_at.is_(None),
        )
    )
    if tl is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "No active trip_load membership for this load", "code": "TRIP_LOAD_NOT_FOUND"},
        )

    now = datetime.now(timezone.utc)
    tl.status_within_trip = TRIP_LOAD_STATUS_WITHIN_REMOVED
    tl.removed_at = now
    await db.flush()

    await _sync_load_active_trip_pointer(db, tenant_id, load_id)

    detail = await get_trip_detail(db, tenant_id, trip_id)
    assert detail is not None
    return detail


async def cancel_trip_manual(db: AsyncSession, tenant_id: int, trip_id: int) -> TripDetailResponse:
    trip = await db.get(Trip, trip_id)
    if trip is None or trip.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.status == TRIP_CONTAINER_STATUS_CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Trip already cancelled", "code": "TRIP_ALREADY_CANCELLED"},
        )

    now = datetime.now(timezone.utc)
    trip.status = TRIP_CONTAINER_STATUS_CANCELLED
    trip.cancelled_at = now
    trip.updated_at = now

    trows = (
        await db.scalars(
            select(TripLoad).where(
                TripLoad.tenant_id == tenant_id,
                TripLoad.trip_id == trip_id,
                TripLoad.removed_at.is_(None),
            )
        )
    ).all()

    affected: set[int] = set()
    for tl in trows:
        affected.add(int(tl.load_id))
        tl.status_within_trip = TRIP_LOAD_STATUS_WITHIN_REMOVED
        tl.removed_at = now

    await db.flush()

    for lid in affected:
        await _sync_load_active_trip_pointer(db, tenant_id, lid)

    drift = (
        await db.scalars(select(Load).where(Load.tenant_id == tenant_id, Load.active_trip_id == trip_id))
    ).all()
    for load in drift:
        await _sync_load_active_trip_pointer(db, tenant_id, int(load.id))

    detail = await get_trip_detail(db, tenant_id, trip_id)
    assert detail is not None
    return detail
