"""Subscription / feature gates (platform DB). Server-side only."""

from __future__ import annotations

from typing import Final

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.models.platform import PlatformSubscription, SubscriptionStatus

# Human-readable labels for 403 messages (same subscription rule until per-plan flags exist).
_ENTITLEMENT_LABELS: Final[dict[str, str]] = {
    "payroll": "Payroll",
    "email_inbox": "Email inbox",
    "email_mailbox": "Email mailbox configuration",
    "admin_sensitive": "Workspace admin tools",
    "driver_documents": "Driver documents",
    "onboarding": "Driver onboarding",
}


async def _ensure_active_subscription(db: AsyncSession, tenant_id: int, feature: str) -> None:
    label = _ENTITLEMENT_LABELS.get(feature, "This feature")
    sub = await db.scalar(
        select(PlatformSubscription)
        .where(PlatformSubscription.tenant_id == tenant_id)
        .order_by(PlatformSubscription.id.desc())
        .limit(1)
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{label} is not available for this workspace (no subscription).",
        )
    if sub.status not in (SubscriptionStatus.TRIAL_ACTIVE.value, SubscriptionStatus.ACTIVE.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{label} is not available while subscription is inactive.",
        )


def _make_entitlement_dep(feature: str):
    async def _dep(
        user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        await _ensure_active_subscription(db, user.tenant_id, feature)

    _dep.__name__ = f"require_{feature}_entitlement"
    _dep.__doc__ = f"Entitlement gate for {feature}."
    return _dep


require_payroll_entitlement = _make_entitlement_dep("payroll")
require_email_inbox_entitlement = _make_entitlement_dep("email_inbox")
require_email_mailbox_entitlement = _make_entitlement_dep("email_mailbox")
require_admin_sensitive_entitlement = _make_entitlement_dep("admin_sensitive")
require_driver_documents_entitlement = _make_entitlement_dep("driver_documents")

_ENTITLEMENT_REGISTRY: dict[str, object] = {
    "payroll": require_payroll_entitlement,
    "email_inbox": require_email_inbox_entitlement,
    "email_mailbox": require_email_mailbox_entitlement,
    "admin_sensitive": require_admin_sensitive_entitlement,
    "driver_documents": require_driver_documents_entitlement,
}


def require_entitlement(feature: str):
    """
    Return the dependency callable for a feature (use as Depends(require_entitlement("payroll"))).
    """
    dep = _ENTITLEMENT_REGISTRY.get(feature)
    if dep is None:
        raise ValueError(f"Unknown entitlement feature: {feature}")
    return dep


async def require_tenant_subscription_active(
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Same subscription rule as feature entitlements, for routes that use token/query auth (no JWT).
    Blocks invite/applicant flows when subscription is missing or not TRIAL_ACTIVE/ACTIVE.
    """
    await _ensure_active_subscription(db, tenant_id, "onboarding")
