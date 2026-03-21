from __future__ import annotations

from datetime import date
from typing import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker
from app.models.driver import Driver
from app.models.load import Load, LoadNote
from app.models.truck import Truck
from app.models.trailer import Trailer
from app.schemas.load import LoadCreate, LoadUpdate, ALLOWED_STATUSES
from app.utils.pagination import paginate


async def _get_driver(db: AsyncSession, tenant_id: int, driver_id: int) -> Driver | None:
    result = await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _get_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> Broker | None:
    result = await db.execute(select(Broker).where(Broker.id == broker_id, Broker.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _get_truck(db: AsyncSession, tenant_id: int, truck_id: int) -> Truck | None:
    result = await db.execute(select(Truck).where(Truck.id == truck_id, Truck.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _get_trailer(db: AsyncSession, tenant_id: int, trailer_id: int) -> Trailer | None:
    result = await db.execute(select(Trailer).where(Trailer.id == trailer_id, Trailer.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _ensure_unique_load_number(db: AsyncSession, tenant_id: int, load_number: str, exclude_id: int | None = None):
    stmt = select(Load).where(Load.tenant_id == tenant_id, Load.load_number == load_number)
    if exclude_id:
        stmt = stmt.where(Load.id != exclude_id)
    exists = await db.scalar(stmt.limit(1))
    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A load with this load_number already exists"
        )


async def create_load(db: AsyncSession, tenant_id: int, payload: LoadCreate) -> Load:
    if payload.driver_id is not None and not await _get_driver(db, tenant_id, payload.driver_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver not found")
    if payload.broker_id is not None and not await _get_broker(db, tenant_id, payload.broker_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker not found")
    if payload.truck_id is not None and not await _get_truck(db, tenant_id, payload.truck_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Truck not found")
    if payload.trailer_id is not None and not await _get_trailer(db, tenant_id, payload.trailer_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trailer not found")

    await _ensure_unique_load_number(db, tenant_id, payload.load_number)

    load = Load(**payload.model_dump(), tenant_id=tenant_id)
    db.add(load)
    await db.commit()
    await db.refresh(load)
    return load


async def get_load(db: AsyncSession, tenant_id: int, load_id: int) -> Load | None:
    result = await db.execute(
        select(Load)
        .options(
            selectinload(Load.driver),
            selectinload(Load.broker),
            selectinload(Load.truck),
            selectinload(Load.trailer),
        )
        .where(Load.id == load_id, Load.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def list_loads(
    db: AsyncSession,
    tenant_id: int,
    statuses: Iterable[str] | None = None,
    driver_id: int | None = None,
    broker_id: int | None = None,
    truck_id: int | None = None,
    trailer_id: int | None = None,
    pickup_start: date | None = None,
    pickup_end: date | None = None,
    page: int = 1,
    size: int = 25,
):
    stmt = (
        select(Load)
        .options(
            selectinload(Load.driver),
            selectinload(Load.broker),
            selectinload(Load.truck),
            selectinload(Load.trailer),
        )
        .where(Load.tenant_id == tenant_id)
        .order_by(Load.id.desc())
    )

    if statuses:
        normalized = [s.strip().lower() for s in statuses if s]
        stmt = stmt.where(Load.status.in_([s for s in normalized if s in ALLOWED_STATUSES]))
    if driver_id:
        stmt = stmt.where(Load.driver_id == driver_id)
    if broker_id:
        stmt = stmt.where(Load.broker_id == broker_id)
    if truck_id:
        stmt = stmt.where(Load.truck_id == truck_id)
    if trailer_id:
        stmt = stmt.where(Load.trailer_id == trailer_id)
    if pickup_start:
        stmt = stmt.where(Load.pickup_date >= pickup_start)
    if pickup_end:
        stmt = stmt.where(Load.pickup_date <= pickup_end)

    return await paginate(db, stmt, page=page, size=size)


async def update_load(db: AsyncSession, tenant_id: int, load_id: int, payload: LoadUpdate) -> Load:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    data = payload.model_dump(exclude_unset=True)

    if "driver_id" in data:
        driver_id = data["driver_id"]
        if driver_id is not None and not await _get_driver(db, tenant_id, driver_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver not found")
    if "truck_id" in data:
        truck_id = data["truck_id"]
        if truck_id is not None and not await _get_truck(db, tenant_id, truck_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Truck not found")
    if "trailer_id" in data:
        trailer_id = data["trailer_id"]
        if trailer_id is not None and not await _get_trailer(db, tenant_id, trailer_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trailer not found")

    if "broker_id" in data:
        broker_id = data["broker_id"]
        if broker_id is not None and not await _get_broker(db, tenant_id, broker_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker not found")

    if "load_number" in data and data["load_number"]:
        await _ensure_unique_load_number(db, tenant_id, data["load_number"], exclude_id=load.id)

    for key, value in data.items():
        setattr(load, key, value)

    await db.commit()
    await db.refresh(load)
    return load


async def delete_load(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    await db.delete(load)
    await db.commit()


async def list_loads_for_board(
    db: AsyncSession,
    tenant_id: int,
    search: str | None = None,
) -> dict[str, list]:
    """Return loads grouped by status for dispatch board. No pagination."""
    stmt = (
        select(Load)
        .options(
            selectinload(Load.driver),
            selectinload(Load.broker),
            selectinload(Load.truck),
            selectinload(Load.trailer),
        )
        .where(Load.tenant_id == tenant_id)
        .order_by(Load.id.desc())
    )
    if search and search.strip():
        q = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Load.load_number.ilike(q),
                Load.pickup_location.ilike(q),
                Load.delivery_location.ilike(q),
            )
        )
    result = await db.execute(stmt)
    loads = list(result.scalars().all())

    grouped: dict[str, list] = {s: [] for s in ALLOWED_STATUSES}
    for load in loads:
        s = (load.status or "unassigned").strip().lower()
        if s in grouped:
            grouped[s].append(load)
        else:
            grouped["unassigned"].append(load)
    return grouped


async def add_load_note(
    db: AsyncSession, tenant_id: int, load_id: int, body: str, author_user_id: str | None = None
) -> LoadNote:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    note = LoadNote(tenant_id=tenant_id, load_id=load_id, body=body.strip(), author_user_id=author_user_id)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_load_notes(db: AsyncSession, tenant_id: int, load_id: int) -> list[LoadNote]:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    result = await db.execute(
        select(LoadNote).where(LoadNote.load_id == load_id, LoadNote.tenant_id == tenant_id).order_by(LoadNote.created_at.desc())
    )
    return list(result.scalars().all())
