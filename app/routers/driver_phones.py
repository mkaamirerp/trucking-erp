from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.db.session import get_db
from app.models.driver_phone import DriverPhone
from app.schemas.driver_phone import DriverPhoneCreate, DriverPhoneRead

router = APIRouter(prefix="/driver-phones", tags=["Driver Phones"])


@router.get("", response_model=list[DriverPhoneRead])
async def list_driver_phones(
    driver_id: int | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DriverPhone)

    if driver_id is not None:
        stmt = stmt.where(DriverPhone.driver_id == driver_id)

    if not include_inactive:
        stmt = stmt.where(DriverPhone.is_active.is_(True))

    stmt = stmt.order_by(DriverPhone.id.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("", response_model=DriverPhoneRead)
async def create_driver_phone(
    payload: DriverPhoneCreate,
    db: AsyncSession = Depends(get_db),
):
    phone = DriverPhone(**payload.model_dump())
    db.add(phone)
    await db.commit()
    await db.refresh(phone)
    return phone


@router.delete("/{phone_id}", response_model=DriverPhoneRead)
async def deactivate_driver_phone(
    phone_id: int,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    phone = await db.get(DriverPhone, phone_id)
    if not phone:
        raise HTTPException(status_code=404, detail="Driver phone not found")

    if not phone.is_active:
        return phone  # idempotent

    phone.is_active = False
    phone.deactivated_at = datetime.now(timezone.utc)
    phone.deactivated_reason = (reason or "Deactivated").strip()[:255]

    await db.commit()
    await db.refresh(phone)
    return phone


@router.post("/{phone_id}/reactivate", response_model=DriverPhoneRead)
async def reactivate_driver_phone(
    phone_id: int,
    db: AsyncSession = Depends(get_db),
):
    phone = await db.get(DriverPhone, phone_id)
    if not phone:
        raise HTTPException(status_code=404, detail="Driver phone not found")

    phone.is_active = True
    phone.deactivated_at = None
    phone.deactivated_reason = None

    await db.commit()
    await db.refresh(phone)
    return phone
