"""Create a new platform tenant + membership + provision DB for an existing platform user (no new platform_users row)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import (
    OnboardingStatus,
    PlatformOnboardingPayload,
    PlatformSubscription,
    PlatformTenant,
    PlatformTenantMember,
    PlatformUser,
    SubscriptionPlan,
    SubscriptionStatus,
    TenantDBStatus,
    TenantMembership,
    TenantStatus,
)
from app.services.tenant_provisioning import provision_tenant_db


async def provision_new_workspace_for_platform_user(
    db: AsyncSession,
    *,
    user: PlatformUser,
    normalized_slug: str,
    tenant_display_name: str,
    country_code: str | None,
    creator_first_name: str,
    creator_last_name: str,
    now: datetime | None = None,
    onboarding_draft: PlatformOnboardingPayload | None = None,
) -> tuple[PlatformTenant, PlatformTenantMember]:
    """
    Platform DB only until provision_tenant_db runs (same transaction as caller).
    Links onboarding_draft to the new tenant when provided (signup verify-otp path).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    tenant = PlatformTenant(
        name=tenant_display_name,
        slug=normalized_slug,
        status=TenantStatus.PENDING_SETUP.value,
        db_status=TenantDBStatus.NOT_CREATED.value,
        country_code=country_code,
    )
    db.add(tenant)
    await db.flush()

    if onboarding_draft is not None:
        onboarding_draft.tenant_id = tenant.id
        onboarding_draft.status = OnboardingStatus.COMPLETED.value
        onboarding_draft.updated_at = now
        await db.flush()

    membership = PlatformTenantMember(
        tenant_id=tenant.id,
        platform_user_id=user.id,
        role="TENANT_ADMIN",
    )
    db.add(membership)

    gate = TenantMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        status="pending",
        is_break_glass_owner=True,
    )
    db.add(gate)

    subscription = PlatformSubscription(
        tenant_id=tenant.id,
        plan=SubscriptionPlan.TRIAL.value,
        status=SubscriptionStatus.TRIAL_ACTIVE.value,
        trial_ends_at=now + timedelta(days=14),
    )
    db.add(subscription)

    await db.flush()

    tenant = await provision_tenant_db(
        int(tenant.id),
        db,
        activate=True,
        creator_platform_user_id=user.id,
        creator_first_name=creator_first_name,
        creator_last_name=creator_last_name,
        creator_email=user.email,
    )

    gate_row = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == tenant.id,
        )
    )
    if gate_row:
        gate_row.status = "active"

    await db.refresh(membership)
    return tenant, membership
