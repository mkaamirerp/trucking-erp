from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.session import get_db
from app.models.driver import Driver
from app.models.driver_phone import DriverPhone
from app.schemas.driver_phone import DriverPhoneCreate, DriverPhoneUpdate, DriverPhoneRead

router = APIRouter(
    prefix="/drivers/{driver_id}/phones",
    tags=["Driver Phones"],
)


@router.get("", response_model=list[DriverPhoneRead])
async def list_driver_phones(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
):
    driver = await db.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    result = await db.execute(
        select(DriverPhone)
        .where(DriverPhone.driver_id == driver_id)
        .order_by(DriverPhone.is_primary.desc(), DriverPhone.id.asc())
    )
    return result.scalars().all()


@router.post("", response_model=DriverPhoneRead, status_code=status.HTTP_201_CREATED)
async def add_driver_phone(
    driver_id: int,
    payload: DriverPhoneCreate,
    db: AsyncSession = Depends(get_db),
):
    driver = await db.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if payload.is_primary:
        await db.execute(
            update(DriverPhone)
            .where(DriverPhone.driver_id == driver_id)
            .values(is_primary=False)
        )

    phone = DriverPhone(driver_id=driver_id, **payload.model_dump())
    db.add(phone)
    await db.commit()
    await db.refresh(phone)
    return phone


@router.patch("/{phone_id}", response_model=DriverPhoneRead)
async def update_driver_phone(
    driver_id: int,
    phone_id: int,
    payload: DriverPhoneUpdate,
    db: AsyncSession = Depends(get_db),
):
    phone = await db.get(DriverPhone, phone_id)
    if not phone or phone.driver_id != driver_id:
        raise HTTPException(status_code=404, detail="Phone not found")

    data = payload.model_dump(exclude_unset=True)

    if data.get("is_primary") is True:
        await db.execute(
            update(DriverPhone)
            .where(DriverPhone.driver_id == driver_id)
            .values(is_primary=False)
        )

    for k, v in data.items():
        setattr(phone, k, v)

    await db.commit()
    await db.refresh(phone)
    return phone


@router.delete("/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_driver_phone(
    driver_id: int,
    phone_id: int,
    db: AsyncSession = Depends(get_db),
):
    phone = await db.get(DriverPhone, phone_id)
    if not phone or phone.driver_id != driver_id:
        raise HTTPException(status_code=404, detail="Phone not found")

    await db.delete(phone)
    await db.commit()
