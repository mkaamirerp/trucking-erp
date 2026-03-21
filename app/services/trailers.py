"""Trailer CRUD service with tenant isolation."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trailer import Trailer
from app.schemas.trailer import TrailerCreate, TrailerUpdate
from app.utils.pagination import paginate


async def create_trailer(db: AsyncSession, tenant_id: int, payload: TrailerCreate) -> Trailer:
    data = payload.model_dump()
    if data.get("vin"):
        data["vin"] = (data["vin"] or "").strip().upper()
    data["tenant_id"] = tenant_id
    trailer = Trailer(**data)
    db.add(trailer)
    try:
        await db.commit()
        await db.refresh(trailer)
        return trailer
    except Exception as e:
        await db.rollback()
        if "uq_trailers_tenant_unit_number" in str(e) or "uq_trailers_tenant_vin" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unit number or VIN (when provided) already exists for this tenant",
            ) from e
        raise


async def get_trailer(db: AsyncSession, tenant_id: int, trailer_id: int) -> Trailer | None:
    result = await db.execute(
        select(Trailer).where(Trailer.id == trailer_id, Trailer.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def list_trailers(
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
    stmt = select(Trailer).where(Trailer.tenant_id == tenant_id)

    if status_filter:
        stmt = stmt.where(Trailer.status.in_([s.strip().lower() for s in status_filter]))
    if ownership_type:
        stmt = stmt.where(Trailer.ownership_type == ownership_type.strip().lower())
    if unit_number:
        stmt = stmt.where(Trailer.unit_number.ilike(f"%{unit_number.strip()}%"))
    if vin:
        stmt = stmt.where(Trailer.vin == (vin or "").strip().upper())
    if plate_number:
        stmt = stmt.where(Trailer.plate_number.ilike(f"%{plate_number.strip()}%"))

    stmt = stmt.order_by(Trailer.id.desc())
    return await paginate(db, stmt, page=page, size=size)


async def update_trailer(
    db: AsyncSession, tenant_id: int, trailer_id: int, payload: TrailerUpdate
) -> Trailer:
    trailer = await get_trailer(db, tenant_id, trailer_id)
    if not trailer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trailer not found")

    data = payload.model_dump(exclude_unset=True)
    if data.get("vin") is not None and data["vin"]:
        data["vin"] = data["vin"].strip().upper()
    for key, value in data.items():
        setattr(trailer, key, value)
    if data.get("trailer_type") and data["trailer_type"] != "reefer":
        trailer.reefer_make = None
        trailer.reefer_model = None
        trailer.reefer_serial = None

    try:
        await db.commit()
        await db.refresh(trailer)
        return trailer
    except Exception as e:
        await db.rollback()
        if "uq_trailers_tenant_unit_number" in str(e) or "uq_trailers_tenant_vin" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unit number or VIN (when provided) already exists for this tenant",
            ) from e
        raise
