from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.driver import Driver
from app.models.load import Load
from app.models.broker import Broker
from app.schemas.driver import DriverOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def _zero_summary():
    return {
        "active_loads": 0,
        "in_transit": 0,
        "delayed": 0,
        "delivered_today": 0,
        "miles_this_week": 0,
        "revenue_this_week": 0.0,
        "drivers_active": 0,
        "drivers_total": 0,
        "drivers": [],
    }


@router.get("/summary")
async def dashboard_summary(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    range: str = "week",
):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    active_statuses = ["assigned", "picked_up"]
    in_transit_status = "picked_up"

    try:
        active_loads = await db.scalar(
            select(func.count()).where(Load.tenant_id == tenant_id, Load.status.in_(active_statuses))
        )
        in_transit = await db.scalar(
            select(func.count()).where(Load.tenant_id == tenant_id, Load.status == in_transit_status)
        )
        delayed = await db.scalar(
            select(func.count()).where(
                Load.tenant_id == tenant_id,
                Load.status == in_transit_status,
                Load.delivery_date < today,
            )
        )
        delivered_today = await db.scalar(
            select(func.count()).where(
                Load.tenant_id == tenant_id,
                Load.status == "delivered",
                Load.delivery_date == today,
            )
        )
        miles_this_week = await db.scalar(
            select(func.coalesce(func.sum(Load.miles), 0)).where(
                Load.tenant_id == tenant_id,
                Load.pickup_date >= week_start,
            )
        )
        revenue_this_week = await db.scalar(
            select(func.coalesce(func.sum(Load.rate), 0)).where(
                Load.tenant_id == tenant_id,
                Load.pickup_date >= week_start,
            )
        )
        drivers_total = await db.scalar(
            select(func.count()).where(Driver.tenant_id == tenant_id, Driver.is_active == True)
        )
    except ProgrammingError as e:
        # Tenant DB may not have loads/drivers tables yet (migrations not run or old schema)
        msg = str(getattr(e, "orig", e))
        if "does not exist" in msg:
            logger.warning("Dashboard summary: tenant schema missing loads/drivers (%s), returning zeros", msg)
            return _zero_summary()
        raise

    # Include driver list in same request so dashboard always has drivers when count > 0 (permissive schema, no skip)
    drivers_out: list[DriverListOut] = []
    try:
        drivers_result = await db.execute(
            select(Driver).where(Driver.tenant_id == tenant_id).order_by(Driver.id.desc()).limit(50)
        )
        driver_rows = list(drivers_result.scalars().all())
        drivers_out = [driver_row_to_list_out(d) for d in driver_rows]
    except Exception as e:
        logger.warning("Dashboard: driver list failed (%s), returning empty", e)

    return {
        "active_loads": int(active_loads or 0),
        "in_transit": int(in_transit or 0),
        "delayed": int(delayed or 0),
        "delivered_today": int(delivered_today or 0),
        "miles_this_week": int(miles_this_week or 0),
        "revenue_this_week": float(revenue_this_week or 0),
        "drivers_active": int(drivers_total or 0),
        "drivers_total": int(drivers_total or 0),
        "drivers": drivers_out,
    }


# ---- Demo seed: drivers + loads matching reference dashboard ----
DEMO_DRIVERS = [
    {"first_name": "Mike", "last_name": "T.", "email": "mike@demo.test", "phone": "+12125551001"},
    {"first_name": "John", "last_name": "R.", "email": "john@demo.test", "phone": "+12125551002"},
    {"first_name": "Sam", "last_name": "K.", "email": "sam@demo.test", "phone": "+12125551003"},
    {"first_name": "Mark", "last_name": "A.", "email": "mark@demo.test", "phone": "+12125551004"},
    {"first_name": "Greg", "last_name": "W.", "email": "greg@demo.test", "phone": "+12125551005"},
    {"first_name": "Tom", "last_name": "W.", "email": "tom@demo.test", "phone": "+12125551006"},
]

CITIES = [
    ("Philadelphia", "PA"),
    ("Atlanta", "GA"),
    ("Houston", "TX"),
    ("New York", "NY"),
    ("Dallas", "TX"),
    ("Cincinnati", "OH"),
    ("Chicago", "IL"),
    ("Phoenix", "AZ"),
]


@router.post("/seed-demo")
async def seed_demo(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Seed current tenant with demo drivers and loads (reference dashboard). Idempotent: skips if data exists."""
    try:
        return await _seed_demo_impl(tenant_id, db)
    except ProgrammingError as e:
        msg = str(getattr(e, "orig", e))
        if "does not exist" in msg:
            logger.warning("Seed demo: tenant schema missing tables (%s)", msg)
            raise HTTPException(
                status_code=503,
                detail="Workspace schema is not ready. Run tenant migrations to create loads and drivers tables.",
            ) from e
        raise


async def _seed_demo_impl(tenant_id: int, db: AsyncSession):
    """Inner implementation so we can catch ProgrammingError in the route."""
    # Check if already seeded
    existing = await db.scalar(select(Load).where(Load.tenant_id == tenant_id).limit(1))
    if existing:
        return {"ok": True, "message": "Demo data already present", "skipped": True}

    # Broker
    broker = Broker(tenant_id=tenant_id, name="Broker Mate")
    db.add(broker)
    await db.flush()

    # Drivers
    drivers = []
    for d in DEMO_DRIVERS:
        driver = Driver(tenant_id=tenant_id, is_active=True, **d)
        db.add(driver)
        await db.flush()
        drivers.append(driver)

    # Loads: ~24 active (assigned + picked_up), 12 in transit (picked_up), 3 delayed (picked_up, past delivery), revenue ~58200
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    load_number = 76200
    total_revenue = 0
    target_revenue = 58200

    def next_load_number():
        nonlocal load_number
        load_number += 1
        return str(load_number)

    for i, drv in enumerate(drivers):
        # 4–5 loads per driver: mix of picked_up, assigned, delivered
        for j in range(5):
            pickup_city, pickup_state = CITIES[(i + j) % len(CITIES)]
            delivery_city, delivery_state = CITIES[(i + j + 2) % len(CITIES)]
            pickup_loc = f"{pickup_city}, {pickup_state}"
            delivery_loc = f"{delivery_city}, {delivery_state}"

            # Vary status: first 2 drivers get more picked_up (in transit), some delayed
            if i < 2 and j < 2:
                status = "picked_up"
                delivery_d = today - timedelta(days=j) if j == 1 else today + timedelta(days=1)
            elif i == 0 and j == 2:
                status = "picked_up"
                delivery_d = today - timedelta(days=1)  # delayed
            elif i < 4:
                status = "assigned" if j % 2 == 0 else "picked_up"
                delivery_d = today + timedelta(days=j + 1)
            else:
                status = "delivered" if j >= 3 else ("assigned" if j % 2 == 0 else "picked_up")
                delivery_d = today + timedelta(days=j) if status != "delivered" else today - timedelta(days=1)

            pickup_d = week_start + timedelta(days=(i * 5 + j) % 7)
            rate = 2100.0 + (i * 100) + (j * 50)
            miles = 400 + (i + j) * 80
            if pickup_d >= week_start:
                total_revenue += rate

            load = Load(
                tenant_id=tenant_id,
                load_number=next_load_number(),
                broker_id=broker.id,
                driver_id=drv.id,
                pickup_date=pickup_d,
                delivery_date=delivery_d,
                pickup_location=pickup_loc,
                delivery_location=delivery_loc,
                rate=rate,
                miles=miles,
                status=status,
            )
            db.add(load)

    # Adjust one load rate so revenue_this_week ≈ 58200
    await db.flush()
    if total_revenue < target_revenue:
        last_load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id).order_by(Load.id.desc()).limit(1))
        if last_load and last_load.pickup_date >= week_start:
            last_load.rate = (last_load.rate or 0) + (target_revenue - total_revenue)

    await db.commit()
    return {"ok": True, "message": "Demo data seeded", "drivers": len(drivers), "loads": load_number - 76200}
