from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.driver import Driver
from app.models.load import Load

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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

    active_loads = await db.scalar(
        select(func.count()).where(Load.tenant_id == tenant_id, Load.status.in_(active_statuses))
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
    drivers_total = await db.scalar(select(func.count()).where(Driver.tenant_id == tenant_id, Driver.is_active == True))

    return {
        "active_loads": int(active_loads or 0),
        "delivered_today": int(delivered_today or 0),
        "miles_this_week": int(miles_this_week or 0),
        "revenue_this_week": float(revenue_this_week or 0),
        "drivers_active": int(drivers_total or 0),
        "drivers_total": int(drivers_total or 0),
    }
