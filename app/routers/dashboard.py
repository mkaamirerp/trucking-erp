from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.driver import Driver
from app.models.load import Load, LoadStop
from app.schemas.driver import DriverListOut, driver_row_to_list_out

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

    active_statuses = ["assigned", "dispatched", "arrived_pickup", "in_transit", "arrived_delivery"]
    in_transit_status = "in_transit"

    try:
        active_loads = await db.scalar(
            select(func.count()).where(Load.tenant_id == tenant_id, Load.status.in_(active_statuses))
        )
        in_transit = await db.scalar(
            select(func.count()).where(Load.tenant_id == tenant_id, Load.status == in_transit_status)
        )
        # Delayed: in_transit/arrived_delivery with latest DROP appointment_date < today
        drop_max = select(LoadStop.load_id, func.max(LoadStop.appointment_date).label("max_d")).where(
            LoadStop.tenant_id == tenant_id,
            LoadStop.stop_type == "DROP",
            LoadStop.appointment_date.isnot(None),
        ).group_by(LoadStop.load_id).subquery()
        delayed = await db.scalar(
            select(func.count()).select_from(Load)
            .join(drop_max, Load.id == drop_max.c.load_id)
            .where(
                Load.tenant_id == tenant_id,
                Load.status.in_([in_transit_status, "arrived_delivery"]),
                drop_max.c.max_d < today,
            )
        )
        delivered_today = await db.scalar(
            select(func.count()).select_from(Load)
            .join(LoadStop, and_(Load.id == LoadStop.load_id, LoadStop.stop_type == "DROP", LoadStop.appointment_date == today))
            .where(Load.tenant_id == tenant_id, Load.status == "delivered")
        )
        pickup_in_week = select(Load.id).join(
            LoadStop, and_(Load.id == LoadStop.load_id, LoadStop.stop_type == "PICKUP", LoadStop.appointment_date >= week_start)
        ).where(Load.tenant_id == tenant_id)
        miles_this_week = await db.scalar(
            select(func.coalesce(func.sum(Load.miles), 0)).where(Load.tenant_id == tenant_id, Load.id.in_(pickup_in_week))
        )
        revenue_this_week = await db.scalar(
            select(func.coalesce(func.sum(Load.rate), 0)).where(Load.tenant_id == tenant_id, Load.id.in_(pickup_in_week))
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
    try:
        drivers_result = await db.execute(
            select(Driver).where(Driver.tenant_id == tenant_id).order_by(Driver.id.desc()).limit(50)
        )
        driver_rows = list(drivers_result.scalars().all())
        drivers_out = [driver_row_to_list_out(d) for d in driver_rows]
    except SQLAlchemyError as e:
        logger.exception("Dashboard: driver list database error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Dashboard driver list could not be loaded (database error).",
                "code": "DASHBOARD_DRIVERS_LIST_DB_ERROR",
            },
        ) from e
    except ValidationError as e:
        logger.exception("Dashboard: driver list serialization failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "detail": "Dashboard driver list could not be serialized.",
                "code": "DASHBOARD_DRIVERS_LIST_SERIALIZE_ERROR",
            },
        ) from e

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
