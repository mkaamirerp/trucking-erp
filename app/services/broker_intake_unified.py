"""Tenant-first booking broker resolution with read-only global fallback and optional materialization."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker
from app.services.broker_global_materialize import ensure_tenant_broker_from_global, get_tenant_broker_auto_create_from_global
from app.services.broker_intake_resolve import BrokerIntakeResolveResult, resolve_broker_for_intake_from_header
from app.services.global_broker_intake_resolve import (
    resolve_global_broker_by_mc_dot,
    resolve_global_broker_for_intake_from_header,
)


async def _with_intake_signal_conflict(
    tenant_db: AsyncSession,
    base: BrokerIntakeResolveResult,
    tenant_id: int,
    supplemental_mc: str | None,
    supplemental_dot: str | None,
    platform_db: AsyncSession,
) -> BrokerIntakeResolveResult:
    """If tenant broker is logically linked to a global id, supplemental MC/DOT must not point elsewhere."""
    if not base.broker_id:
        return base
    if not supplemental_mc and not supplemental_dot:
        return base
    sup = await resolve_global_broker_by_mc_dot(platform_db, supplemental_mc, supplemental_dot)
    if sup.ambiguous or sup.global_broker_id is None:
        return base
    br = await tenant_db.scalar(
        select(Broker).where(Broker.id == base.broker_id, Broker.tenant_id == tenant_id)
    )
    if not br or br.platform_global_broker_id is None:
        return base
    if int(br.platform_global_broker_id) != int(sup.global_broker_id):
        return replace(base, intake_signal_conflict=True)
    return base


async def resolve_booking_broker_for_email_intake(
    tenant_db: AsyncSession,
    tenant_id: int,
    from_header: str | None,
    *,
    platform_db: AsyncSession,
    supplemental_mc: str | None = None,
    supplemental_dot: str | None = None,
) -> BrokerIntakeResolveResult:
    """
    Resolver order: tenant workspace (known sender → domain → alias, with intake_blocked semantics),
    then **approved** global reference (header path: known sender → domain → alias; supplemental Tier **D**: MC/DOT),
    then caller may apply a **tenant-configured** default broker only when explicitly supported (not hardcoded).

    Tenants never write global rows; global is read-only here. Materialization creates tenant ``brokers`` rows only
    for global header tiers A–C, never for Tier **D** (MC/DOT-only) in this path.

    ``platform_global_broker_id`` on tenant rows is a **logical** link—not a cross-database FK; global rows may be
    absent or stale without affecting tenant DB constraints.
    """
    tenant_res = await resolve_broker_for_intake_from_header(tenant_db, tenant_id, from_header)
    if tenant_res.ambiguous or tenant_res.blocked_match:
        return tenant_res
    if tenant_res.broker_id is not None:
        return await _with_intake_signal_conflict(
            tenant_db,
            tenant_res,
            tenant_id,
            supplemental_mc,
            supplemental_dot,
            platform_db,
        )

    g_hdr = await resolve_global_broker_for_intake_from_header(platform_db, from_header)
    if g_hdr.ambiguous:
        return BrokerIntakeResolveResult(
            None,
            None,
            None,
            ambiguous=True,
            is_global_ambiguous=True,
        )

    g_sup = await resolve_global_broker_by_mc_dot(platform_db, supplemental_mc, supplemental_dot)
    if g_sup.ambiguous:
        return BrokerIntakeResolveResult(
            None,
            None,
            None,
            ambiguous=True,
            is_global_ambiguous=True,
        )

    if (
        g_hdr.global_broker_id is not None
        and g_sup.global_broker_id is not None
        and g_hdr.global_broker_id != g_sup.global_broker_id
    ):
        return BrokerIntakeResolveResult(
            None,
            None,
            None,
            global_identity_disagreement=True,
        )

    if g_hdr.global_broker_id is not None:
        effective_id = g_hdr.global_broker_id
        effective_label = g_hdr.broker_label
        effective_method = g_hdr.match_method
    elif g_sup.global_broker_id is not None:
        effective_id = g_sup.global_broker_id
        effective_label = g_sup.broker_label
        effective_method = g_sup.match_method
    else:
        return BrokerIntakeResolveResult(None, None, None)

    tier_d = effective_method in ("global_exact_mc", "global_exact_dot", "global_exact_mc_dot")
    if tier_d:
        return BrokerIntakeResolveResult(
            None,
            effective_label,
            effective_method,
            platform_global_broker_id=effective_id,
            global_tier_d_requires_review=True,
        )

    auto = await get_tenant_broker_auto_create_from_global(platform_db, tenant_id)
    if auto:
        bid, label = await ensure_tenant_broker_from_global(
            tenant_db,
            platform_db,
            tenant_id,
            effective_id,
            effective_method,
        )
        return BrokerIntakeResolveResult(
            bid,
            label,
            effective_method,
            platform_global_broker_id=effective_id,
        )

    return BrokerIntakeResolveResult(
        None,
        effective_label,
        effective_method,
        platform_global_broker_id=effective_id,
        global_match_no_workspace=True,
    )
