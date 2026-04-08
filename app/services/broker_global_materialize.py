"""Create tenant broker rows from approved global booking reference (policy-gated).

Tier **D** (MC/DOT-only global hits) does not use this module — unified intake returns review instead.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker
from app.models.global_booking_broker import GlobalBookingBroker
from app.models.platform import PlatformTenant


async def get_tenant_broker_auto_create_from_global(platform_db: AsyncSession, tenant_id: int) -> bool:
    val = await platform_db.scalar(
        select(PlatformTenant.broker_auto_create_from_global).where(PlatformTenant.id == tenant_id)
    )
    if val is None:
        return True
    return bool(val)


async def ensure_tenant_broker_from_global(
    tenant_db: AsyncSession,
    platform_db: AsyncSession,
    tenant_id: int,
    global_broker_id: int,
    match_method: str | None,
) -> tuple[int, str]:
    """Return existing or new tenant broker id + display label for intake snapshot."""
    existing = await tenant_db.scalar(
        select(Broker).where(
            Broker.tenant_id == tenant_id,
            Broker.platform_global_broker_id == global_broker_id,
        )
    )
    if existing:
        label = (existing.display_name or existing.legal_name or existing.name or "").strip() or existing.name
        return existing.id, label

    gb = await platform_db.scalar(select(GlobalBookingBroker).where(GlobalBookingBroker.id == global_broker_id))
    if gb is None or (gb.canonical_status or "").lower() != "approved":
        raise ValueError("global broker missing or not approved")

    name = (gb.name or "").strip() or "Unknown broker"
    disp = (gb.display_name or gb.legal_name or name).strip()
    needs_review = match_method == "global_alias"
    row = Broker(
        tenant_id=tenant_id,
        name=name,
        legal_name=gb.legal_name,
        display_name=disp or None,
        mc_number=gb.mc_number,
        dot_number=gb.dot_number,
        auto_created=True,
        auto_create_origin="global_reference_match",
        auto_create_needs_review=needs_review,
        platform_global_broker_id=global_broker_id,
    )
    tenant_db.add(row)
    await tenant_db.flush()
    return row.id, disp or name
