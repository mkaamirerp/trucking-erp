from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.driver import Driver
from app.schemas.driver import DriverCreate, DriverOut, DriverUpdate
from app.deps.tenant import require_tenant

router = APIRouter(prefix="/drivers", tags=["drivers"])

@router.post("", response_model=DriverOut, status_code=status.HTTP_201_CREATED)
async def create_driver(
    payload: DriverCreate,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    driver = Driver(**payload.model_dump(), tenant_id=tenant_id)
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    return driver

@router.get("", response_model=list[DriverOut])
async def list_drivers(
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    include_inactive: bool = False,
):
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
    return list(result.scalars().all())

@router.get("/{driver_id}", response_model=DriverOut)
async def get_driver(
    driver_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
