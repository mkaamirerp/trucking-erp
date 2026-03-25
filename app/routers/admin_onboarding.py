"""Admin-only onboarding: invite link generation (tenant-scoped)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.application_access_token import ApplicationAccessToken
from app.models.person_application import APPLICATION_TYPES, PersonApplication
from app.models.platform import OnboardingTokenLookup, PlatformTenant
from app.schemas.driver_onboarding import DriverOnboardingStatus
from app.deps.admin import is_tenant_admin
from app.utils.email import send_onboarding_invite_email

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/onboarding",
    tags=["Admin Onboarding"],
    dependencies=[Depends(require_entitlement("admin_sensitive"))],
)


class InviteLinkRequest(BaseModel):
    """At least one of email or phone required. application_type required (controls form/workflow)."""
    email: str | None = None
    phone: str | None = None
    application_type: str = "DRIVER"

    @model_validator(mode="after")
    def require_email_or_phone(self):
        if not (self.email or self.phone):
            raise ValueError("Provide at least one of email or phone.")
        return self

    @field_validator("application_type")
    @classmethod
    def validate_application_type(cls, v: str) -> str:
        val = (v or "DRIVER").strip().upper()
        if val not in APPLICATION_TYPES:
            raise ValueError(
                f"application_type must be one of: {', '.join(sorted(APPLICATION_TYPES))}"
            )
        return val


class InviteLinkResponse(BaseModel):
    application_id: int
    token: str
    link: str
    email_sent: bool = False
    email_error: str | None = None  # Safe message when send failed (e.g. SMTP not configured)


@router.post("/invite-link", response_model=InviteLinkResponse)
async def create_invite_link(
    request: Request,
    body: InviteLinkRequest,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")

    tenant = await platform_db.scalar(
        select(PlatformTenant)
        .options(selectinload(PlatformTenant.company_profile))
        .where(PlatformTenant.id == tenant_id)
    )
    tenant_country = (
        (tenant.company_profile.address_country if tenant and tenant.company_profile else None)
        or (tenant.country_code if tenant else None)
        or "US"
    )
    tenant_region = tenant.company_profile.address_region if tenant and tenant.company_profile else None

    application_type = body.application_type
    requested_role_code = application_type  # MVP: same as application_type

    # Create person_application as DRAFT; application_type controls form, requested_role_code used on approval
    app = PersonApplication(
        tenant_id=tenant_id,
        application_type=application_type,
        requested_role_code=requested_role_code,
        status=DriverOnboardingStatus.DRAFT.value,
        source="invite_link",
        email=(body.email or "").strip() or None,
        phone=(body.phone or "").strip() or None,
        intake_payload={
            "step": "dl_upload" if application_type == "DRIVER" else "common",
            "form_country_default": tenant_country,
            "form_region_default": tenant_region,
        },
    )
    db.add(app)
    await db.flush()

    # Token: secure, unique; store hash in tenant DB only; return raw token once (for link + optional platform bridge)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=60)
    access = ApplicationAccessToken(
        tenant_id=tenant_id,
        application_id=app.id,
        token=token,
        token_hash=token_hash,
        expires_at=expires_at,
        revoked_at=None,
    )
    db.add(access)
    await db.commit()
    await db.refresh(access)

    logger.info(
        "Invite token created: application_id=%s tenant_id=%s token_present=%s token_hash_present=%s expires_at=%s revoked_at=%s",
        app.id,
        tenant_id,
        access.token is not None,
        access.token_hash is not None,
        access.expires_at,
        access.revoked_at,
    )

    # Platform: optional bridge for redirect-only (e.g. map token -> slug); applicant auth is tenant DB only
    platform_db.add(
        OnboardingTokenLookup(
            token=token,
            tenant_id=tenant_id,
            application_id=app.id,
            expires_at=expires_at,
        )
    )
    await platform_db.commit()

    # Link using current host (e.g. xyz.truckerp.me)
    base = str(request.base_url).rstrip("/")
    link = f"{base}/onboarding?token={token}"

    email_sent = False
    email_error: str | None = None
    if body.email and (email := (body.email or "").strip()):
        try:
            await send_onboarding_invite_email(to=email, invite_link=link)
            email_sent = True
        except Exception as exc:
            logger.exception("Invite link email failed to %s: %s", email, exc)
            email_error = (
                "Could not send email. Check that SMTP is configured in your environment (e.g. SSM: "
                "SMTP_HOST, SMTP_FROM_ADDRESS, SMTP_USERNAME, SMTP_PASSWORD). See server logs for details."
            )

    return InviteLinkResponse(
        application_id=app.id, token=token, link=link, email_sent=email_sent, email_error=email_error
    )
