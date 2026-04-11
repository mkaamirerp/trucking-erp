import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps.auth import get_current_user

logger = logging.getLogger(__name__)
from app.models.driver import Driver
from app.models.load import Load, LoadStop
from app.schemas.driver import DriverCreate, DriverOut, DriverUpdate, DriverListOut, driver_row_to_list_out
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db

router = APIRouter(prefix="/drivers", tags=["drivers"])
# Operational dispatch roster: rows in `drivers` (not PersonApplication drafts). DRIVER approvals
# materialize rows via driver_onboarding; admin may also POST here explicitly.

@router.post("", response_model=DriverOut, status_code=status.HTTP_201_CREATED)
async def create_driver(
    payload: DriverCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Explicit operational admin create for the dispatch roster (`drivers` table).

    This is not the onboarding approval path; canonical DRIVER PersonApplication approval
    materializes or consolidates rows in the same table via driver_onboarding (see
    `_upsert_operational_driver_for_person`).
    """
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
    """List approved operational drivers for dispatch (tenant `drivers` table)."""
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

    try:
        result = await db.execute(stmt)
    except SQLAlchemyError as e:
        logger.exception("list_drivers database error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Driver list could not be loaded (database error).",
                "code": "DRIVERS_LIST_DB_ERROR",
            },
        ) from e

    rows = list(result.scalars().all())
    try:
        return [driver_row_to_list_out(d) for d in rows]
    except ValidationError as e:
        logger.exception("list_drivers serialization failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "detail": "Driver list could not be serialized.",
                "code": "DRIVERS_LIST_SERIALIZE_ERROR",
            },
        ) from e

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

    pickup_in_week = select(Load.id).join(
        LoadStop, and_(Load.id == LoadStop.load_id, LoadStop.stop_type == "PICKUP", LoadStop.appointment_date >= week_start)
    ).where(Load.tenant_id == tenant_id, Load.driver_id == driver_id)
    miles_week = await db.scalar(
        select(func.coalesce(func.sum(Load.miles), 0)).where(
            Load.tenant_id == tenant_id,
            Load.driver_id == driver_id,
            Load.id.in_(pickup_in_week),
        )
    )
    revenue_week = await db.scalar(
        select(func.coalesce(func.sum(Load.rate), 0)).where(
            Load.tenant_id == tenant_id,
            Load.driver_id == driver_id,
            Load.id.in_(pickup_in_week),
        )
    )
    active_loads = await db.scalar(
        select(func.count()).where(
            Load.tenant_id == tenant_id,
            Load.driver_id == driver_id,
            Load.status.in_(["assigned", "dispatched", "arrived_pickup", "in_transit", "arrived_delivery"]),
        )
    )
    first_pu = select(Load.id, func.min(LoadStop.appointment_date).label("pu_date")).select_from(Load).join(
        LoadStop, and_(Load.id == LoadStop.load_id, LoadStop.stop_type == "PICKUP")
    ).where(
        Load.tenant_id == tenant_id,
        Load.driver_id == driver_id,
        ~Load.status.in_(["delivered", "issue_hold"]),
    ).group_by(Load.id).subquery()
    upcoming_stmt = (
        select(Load)
        .options(selectinload(Load.stops))
        .join(first_pu, Load.id == first_pu.c.id)
        .where(first_pu.c.pu_date >= today)
        .order_by(first_pu.c.pu_date.asc())
        .limit(10)
    )
    upcoming_result = await db.execute(upcoming_stmt)
    upcoming_loads = list(upcoming_result.scalars().unique().all())

    def _pickup_display(load):
        pu = next((s for s in load.stops if s.stop_type.upper() == "PICKUP"), None)
        return pu.appointment_date if pu else None

    def _delivery_display(load):
        dr = next((s for s in reversed(load.stops) if s.stop_type.upper() == "DROP"), None)
        return dr.appointment_date if dr else None

    def _pickup_loc(load):
        pu = next((s for s in load.stops if s.stop_type.upper() == "PICKUP"), None)
        if pu and (pu.facility_name or pu.city):
            return pu.facility_name or f"{pu.city or ''}, {pu.state_or_province or ''}".strip(", ")
        return None

    def _delivery_loc(load):
        dr = next((s for s in reversed(load.stops) if s.stop_type.upper() == "DROP"), None)
        if dr and (dr.facility_name or dr.city):
            return dr.facility_name or f"{dr.city or ''}, {dr.state_or_province or ''}".strip(", ")
        return None

    driver_data = {
        "id": driver.id,
        "first_name": driver.first_name,
        "last_name": driver.last_name,
        "phone": driver.phone,
        "email": driver.email,
        "license_number": driver.license_number,
        "license_expiry": driver.license_expiry_date,
        "notes": None,
        "is_active": driver.is_active,
    }

    upcoming_items = [
        {
            "id": l.id,
            "load_number": l.load_number,
            "pickup_date": _pickup_display(l),
            "delivery_date": _delivery_display(l),
            "pickup_location": _pickup_loc(l),
            "delivery_location": _delivery_loc(l),
            "status": l.status,
        }
        for l in upcoming_loads
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
