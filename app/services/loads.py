from __future__ import annotations

from datetime import date
from typing import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker
from app.models.driver import Driver
from app.models.load import Load
from app.schemas.load import LoadCreate, LoadUpdate, ALLOWED_STATUSES
from app.utils.pagination import paginate


async def _get_driver(db: AsyncSession, tenant_id: int, driver_id: int) -> Driver | None:
    result = await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _get_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> Broker | None:
    result = await db.execute(select(Broker).where(Broker.id == broker_id, Broker.tenant_id == tenant_id))
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

    await _ensure_unique_load_number(db, tenant_id, payload.load_number)

    load = Load(**payload.model_dump(), tenant_id=tenant_id)
    db.add(load)
    await db.commit()
    await db.refresh(load)
    return load


async def get_load(db: AsyncSession, tenant_id: int, load_id: int) -> Load | None:
    result = await db.execute(
        select(Load)
        .options(selectinload(Load.driver), selectinload(Load.broker))
        .where(Load.id == load_id, Load.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def list_loads(
    db: AsyncSession,
    tenant_id: int,
    statuses: Iterable[str] | None = None,
    driver_id: int | None = None,
    broker_id: int | None = None,
    pickup_start: date | None = None,
    pickup_end: date | None = None,
    page: int = 1,
    size: int = 25,
):
    stmt = (
        select(Load)
        .options(selectinload(Load.driver), selectinload(Load.broker))
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
