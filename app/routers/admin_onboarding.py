"""Admin-only onboarding: invite link generation (tenant-scoped)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.application_access_token import ApplicationAccessToken
from app.models.person_application import PersonApplication
from app.models.platform import OnboardingTokenLookup
from app.schemas.driver_onboarding import DriverOnboardingStatus
from app.utils.email import send_onboarding_invite_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/onboarding", tags=["Admin Onboarding"])


def _is_admin(user: CurrentUser) -> bool:
    role = (user.role or "").upper()
    return role in {"OWNER", "ADMIN", "TENANT_ADMIN"}


class InviteLinkRequest(BaseModel):
    """At least one of email or phone required (who to send the link to)."""
    email: str | None = None
    phone: str | None = None

    @model_validator(mode="after")
    def require_email_or_phone(self):
        if not (self.email or self.phone):
            raise ValueError("Provide at least one of email or phone.")
        return self


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
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")

    # Create person_application as DRAFT; IN_PROGRESS starts when applicant submits (later)
    app = PersonApplication(
        tenant_id=tenant_id,
        status=DriverOnboardingStatus.DRAFT.value,
        source="invite_link",
        email=(body.email or "").strip() or None,
        phone=(body.phone or "").strip() or None,
        intake_payload={"step": "dl_upload"},
    )
    db.add(app)
    await db.flush()

    # Token: secure, unique; expires in 60 days (invalidated on approve/reject)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=60)
    access = ApplicationAccessToken(
        tenant_id=tenant_id,
        application_id=app.id,
        token=token,
        expires_at=expires_at,
    )
    db.add(access)
    await db.commit()

    # Platform: token lookup so applicant routes resolve tenant from token (no host required)
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
