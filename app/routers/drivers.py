import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.authz import require_tenant_admin
from app.deps.auth import get_current_user

logger = logging.getLogger(__name__)
from app.models.driver import Driver
from app.models.load import Load, LoadStop
from app.schemas.dispatch_hints import DriverAssignmentHintsOut
from app.services.equipment_assignment_context import (
    assignment_suggestion_to_hints,
    suggest_assignment_for_driver,
)
from app.schemas.driver import DriverCreate, DriverOut, DriverUpdate, DriverListOut, driver_row_to_list_out
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.policies.people_first_operational_projection import (
    drivers_patch_blocked_canonical_fields,
    people_first_operational_patch_conflict_detail,
)

router = APIRouter(prefix="/drivers", tags=["drivers"])


def _normalize_load_stop_type(stop_type: str | None) -> str:
    return (stop_type or "").strip().upper()


def _find_load_stop(stops, *types: str, reverse: bool = False):
    """First matching stop by type; null-safe when stops empty or stop_type is NULL."""
    want = {t.upper() for t in types}
    ordered = list(stops or [])
    if reverse:
        ordered = list(reversed(ordered))
    for stop in ordered:
        if _normalize_load_stop_type(stop.stop_type) in want:
            return stop
    return None
# Operational dispatch roster: projection rows for dispatch (see people-first rule:
# `app/policies/people_first_operational_projection.py` and `.cursor/rules/people-first-operational-projections.mdc`).
# Materialized via onboarding/workflow or explicit POST; not a second master for person truth when person_id is set.

@router.post(
    "",
    response_model=DriverOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tenant_admin)],
)
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


@router.get("/{driver_id}/assignment-hints", response_model=DriverAssignmentHintsOut)
async def get_driver_assignment_hints(
    driver_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Suggest truck/trailer for a driver via shared equipment assignment policy."""
    result = await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    suggestion = await suggest_assignment_for_driver(db, tenant_id, driver_id)
    payload = assignment_suggestion_to_hints(suggestion, anchor_driver_id=driver_id)
    return DriverAssignmentHintsOut(**payload)


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

@router.patch("/{driver_id}", response_model=DriverOut, dependencies=[Depends(require_tenant_admin)])
async def update_driver(
    driver_id: int,
    payload: DriverUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Update dispatch roster fields. If ``person_id`` is set, master-data fields are blocked (People workspace)."""
    result = await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    data = payload.model_dump(exclude_unset=True)

    if driver.person_id is not None:
        blocked = drivers_patch_blocked_canonical_fields(set(data.keys()))
        if blocked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=people_first_operational_patch_conflict_detail(
                    person_id=int(driver.person_id),
                    blocked_fields=blocked,
                    operational_table="drivers",
                    workspace_edit_hint="person core fields and driver profile (license)",
                    operational_fields_hint="is_active, hire_date, termination_date",
                    stable_api_code="use_people_workspace_for_driver_master_data",
                ),
            )

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
        pu = _find_load_stop(load.stops, "PICKUP")
        return pu.appointment_date if pu else None

    def _delivery_display(load):
        dr = _find_load_stop(load.stops, "DROP", reverse=True)
        return dr.appointment_date if dr else None

    def _pickup_loc(load):
        pu = _find_load_stop(load.stops, "PICKUP")
        if pu and (pu.facility_name or pu.city):
            return pu.facility_name or f"{pu.city or ''}, {pu.state_or_province or ''}".strip(", ")
        return None

    def _delivery_loc(load):
        dr = _find_load_stop(load.stops, "DROP", reverse=True)
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
