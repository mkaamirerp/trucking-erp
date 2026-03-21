import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user

logger = logging.getLogger(__name__)
from app.models.driver import Driver
from app.models.load import Load
from app.schemas.driver import DriverCreate, DriverOut, DriverUpdate, DriverListOut, driver_row_to_list_out
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db

router = APIRouter(prefix="/drivers", tags=["drivers"])

@router.post("", response_model=DriverOut, status_code=status.HTTP_201_CREATED)
async def create_driver(
    payload: DriverCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    driver = Driver(**payload.model_dump(), tenant_id=tenant_id)
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    return driver

@router.get("", response_model=list[DriverListOut])
async def list_drivers(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    include_inactive: bool = False,
):
    try:
        stmt = select(Driver).where(Driver.tenant_id == tenant_id).order_by(Driver.id.desc())

        if not include_inactive:
            stmt = stmt.where(Driver.is_active == True)

        if q:
            qq = f"%{q.strip()}%"
            stmt = stmt.where(or_(
                Driver.first_name.ilike(qq),
                Driver.last_name.ilike(qq),
                Driver.email.ilike(qq),
                Driver.phone.ilike(qq),
            ))

        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return [driver_row_to_list_out(d) for d in rows]
    except Exception as e:
        logger.exception("list_drivers failed: %s", e)
        return []

@router.get("/{driver_id}", response_model=DriverOut)
async def get_driver(
    driver_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    result = await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver

@router.patch("/{driver_id}", response_model=DriverOut)
async def update_driver(
    driver_id: int,
    payload: DriverUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    result = await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    data = payload.model_dump(exclude_unset=True)

    # ✅ Cross-field validation with existing DB values (important for PATCH)
    merged = {
        "first_name": data.get("first_name", driver.first_name),
        "last_name": data.get("last_name", driver.last_name),
        "email": data.get("email", driver.email),
        "phone": data.get("phone", driver.phone),
        "hire_date": data.get("hire_date", driver.hire_date),
        "is_active": data.get("is_active", driver.is_active),
        "termination_date": data.get("termination_date", driver.termination_date),
    }

    # Re-validate using DriverCreate (has cross-field rules)
    try:
        DriverCreate(**merged)
    except (ValueError, RequestValidationError) as e:
        # Return a proper 422 instead of 500
        raise HTTPException(status_code=422, detail=str(e))

    for k, v in data.items():
        setattr(driver, k, v)

    await db.commit()
    await db.refresh(driver)
    return driver

@router.api_route("/{driver_id}", methods=["DELETE"], include_in_schema=False)
async def delete_driver(driver_id: int):
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Hard delete is not supported. Use PATCH to deactivate/terminate the driver."
    )


@router.get("/{driver_id}/summary")
async def driver_summary(
    driver_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    driver = await db.scalar(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    miles_week = await db.scalar(
        select(func.coalesce(func.sum(Load.miles), 0)).where(
            Load.tenant_id == tenant_id,
            Load.driver_id == driver_id,
            Load.pickup_date >= week_start,
        )
    )
    revenue_week = await db.scalar(
        select(func.coalesce(func.sum(Load.rate), 0)).where(
            Load.tenant_id == tenant_id,
            Load.driver_id == driver_id,
            Load.pickup_date >= week_start,
        )
    )
    active_loads = await db.scalar(
        select(func.count()).where(
            Load.tenant_id == tenant_id,
            Load.driver_id == driver_id,
            Load.status.in_(["assigned", "dispatched", "arrived_pickup", "in_transit", "arrived_delivery"]),
        )
    )
    upcoming = await db.execute(
        select(Load)
        .where(
            Load.tenant_id == tenant_id,
            Load.driver_id == driver_id,
            ~Load.status.in_(["delivered", "issue_hold"]),
            Load.pickup_date >= today,
        )
        .order_by(Load.pickup_date.asc())
        .limit(10)
    )

    driver_data = {
        "id": driver.id,
        "first_name": driver.first_name,
        "last_name": driver.last_name,
        "phone": driver.phone,
        "email": driver.email,
        "license_number": driver.license_number,
        "license_expiry": driver.license_expiry_date,
        "notes": None,  # placeholder; extend when notes field exists
        "is_active": driver.is_active,
    }

    upcoming_items = [
        {
            "id": l.id,
            "load_number": l.load_number,
            "pickup_date": l.pickup_date,
            "delivery_date": l.delivery_date,
            "pickup_location": l.pickup_location,
            "delivery_location": l.delivery_location,
            "status": l.status,
        }
        for l in upcoming.scalars().all()
    ]

    return {
        "driver": driver_data,
        "stats": {
            "miles_this_week": int(miles_week or 0),
            "revenue_this_week": float(revenue_week or 0),
            "active_loads": int(active_loads or 0),
        },
        "upcoming_loads": upcoming_items,
    }
