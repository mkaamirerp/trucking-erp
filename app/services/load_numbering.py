"""Mint internal load numbers from tenant_load_number_periods (Task 14)."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformTenant
from app.models.tenant_load_number_period import TenantLoadNumberPeriod

DEFAULT_COMPANY_TIMEZONE = "America/Toronto"

_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


async def company_timezone_for_tenant(tenant_id: int) -> ZoneInfo:
    async with AsyncSessionLocal() as platform_db:
        tz_name = await platform_db.scalar(
            select(PlatformTenant.timezone).where(PlatformTenant.id == tenant_id)
        )
    name = (tz_name or "").strip() or DEFAULT_COMPANY_TIMEZONE
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_COMPANY_TIMEZONE)


def format_load_number(local_dt: datetime, sequence: int) -> str:
    mon = _MONTH_ABBR[local_dt.month - 1]
    yy = local_dt.year % 100
    suffix = f"{sequence:04d}" if sequence <= 9999 else str(sequence)
    return f"{mon}-{yy:02d}-{suffix}"


def period_key_for_instant(local_dt: datetime) -> str:
    return f"{local_dt.year:04d}-{local_dt.month:02d}"


async def mint_next_load_number(
    db: AsyncSession,
    tenant_id: int,
    now: datetime | None = None,
) -> str:
    """Lock the tenant period row, increment next_numeric, return formatted load_number.

    Caller must run inside a transaction; this function does not commit.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    tz = await company_timezone_for_tenant(tenant_id)
    local = now.astimezone(tz)
    period = period_key_for_instant(local)

    await db.execute(
        insert(TenantLoadNumberPeriod)
        .values(tenant_id=tenant_id, period=period, next_numeric=1)
        .on_conflict_do_nothing(index_elements=["tenant_id", "period"])
    )
    row = (
        await db.execute(
            select(TenantLoadNumberPeriod)
            .where(
                TenantLoadNumberPeriod.tenant_id == tenant_id,
                TenantLoadNumberPeriod.period == period,
            )
            .with_for_update()
        )
    ).scalar_one()
    n = int(row.next_numeric)
    row.next_numeric = n + 1
    await db.flush()
    return format_load_number(local, n)
