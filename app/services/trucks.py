"""Truck CRUD service with tenant isolation."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.truck import Truck
from app.schemas.truck import TruckCreate, TruckUpdate
from app.utils.pagination import paginate


async def create_truck(db: AsyncSession, tenant_id: int, payload: TruckCreate) -> Truck:
    data = payload.model_dump()
    data["tenant_id"] = tenant_id
    truck = Truck(**data)
    db.add(truck)
    try:
        await db.commit()
        await db.refresh(truck)
        return truck
    except Exception as e:
        await db.rollback()
        if "uq_trucks_tenant_unit_number" in str(e) or "uq_trucks_tenant_vin" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unit number or VIN already exists for this tenant",
            ) from e
        raise


async def get_truck(db: AsyncSession, tenant_id: int, truck_id: int) -> Truck | None:
    result = await db.execute(
        select(Truck).where(Truck.id == truck_id, Truck.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def list_trucks(
    db: AsyncSession,
    tenant_id: int,
    *,
    status_filter: list[str] | None = None,
    ownership_type: str | None = None,
    unit_number: str | None = None,
    vin: str | None = None,
    plate_number: str | None = None,
    page: int = 1,
    size: int = 25,
) -> dict:
    stmt = select(Truck).where(Truck.tenant_id == tenant_id)

    if status_filter:
        stmt = stmt.where(Truck.status.in_([s.strip().lower() for s in status_filter]))
    if ownership_type:
        stmt = stmt.where(Truck.ownership_type == ownership_type.strip().lower())
    if unit_number:
        stmt = stmt.where(Truck.unit_number.ilike(f"%{unit_number.strip()}%"))
    if vin:
        stmt = stmt.where(Truck.vin == (vin or "").strip().upper())
    if plate_number:
        stmt = stmt.where(Truck.plate_number.ilike(f"%{plate_number.strip()}%"))

    stmt = stmt.order_by(Truck.id.desc())
    return await paginate(db, stmt, page=page, size=size)


async def update_truck(
    db: AsyncSession, tenant_id: int, truck_id: int, payload: TruckUpdate
) -> Truck:
    truck = await get_truck(db, tenant_id, truck_id)
    if not truck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(truck, key, value)

    try:
        await db.commit()
        await db.refresh(truck)
        return truck
    except Exception as e:
        await db.rollback()
        if "uq_trucks_tenant_unit_number" in str(e) or "uq_trucks_tenant_vin" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unit number or VIN already exists for this tenant",
            ) from e
        raise
