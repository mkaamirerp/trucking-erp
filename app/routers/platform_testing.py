"""Minimal platform-admin testing tools (platform API key only)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.platform import PlatformTenant
from app.routers.platform_tenants import require_platform_admin_key
from app.services.login_password_abuse import clear_login_password_fail_streak
from app.services.login_unlock_step_up_pending import set_login_step_up_pending_after_unlock
from app.services.sign_in_lock_state import build_sign_in_lock_state
from app.utils.auth_identity import normalize_auth_email
from app.utils.rate_limit import clear_login_unlock_throttles_for_tenant_email

router = APIRouter(prefix="/api/v1/platform", tags=["platform-testing"])
audit_log = logging.getLogger("platform_admin_audit")


class UnlockLoginIn(BaseModel):
    tenant_slug: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., min_length=3, max_length=320)


@router.post("/testing/login-lock-status")
async def testing_login_lock_status(
    payload: UnlockLoginIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
) -> dict[str, Any]:
    """Read-only: streak + tenant+email login/step-up limiter state (not IP)."""
    slug = payload.tenant_slug.strip().lower()
    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == slug))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found for slug")

    tenant_id = int(tenant.id)
    email_norm = normalize_auth_email(payload.email)
    if not email_norm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")

    state = await build_sign_in_lock_state(tenant_id, email_norm)
    return {
        "tenant_id": tenant_id,
        "tenant_slug": tenant.slug,
        "email_norm": email_norm,
        "state": state,
        "note": "IP-based login throttle is not shown here. Multi-API rate state may differ if not on this instance.",
    }


@router.post("/testing/unlock-login")
async def testing_unlock_login(
    payload: UnlockLoginIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
) -> dict[str, Any]:
    """
    Clear password-fail streak + tenant+email login/step-up rate buckets for one workspace user.
    Does not reset password, OTP secrets, or IP-based login throttle.
    """
    slug = payload.tenant_slug.strip().lower()
    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == slug))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found for slug")

    tenant_id = int(tenant.id)
    email_norm = normalize_auth_email(payload.email)
    if not email_norm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")

    state_before = await build_sign_in_lock_state(tenant_id, email_norm)
    had_workspace_sign_in_friction = not bool(
        state_before.get("overall", {}).get("all_clear_for_tenant_email_unlock_tool")
    )

    streak_deleted = await clear_login_password_fail_streak(tenant_id, email_norm)
    rate_cleared = clear_login_unlock_throttles_for_tenant_email(tenant_id, email_norm)
    mandated_next_sign_in_verification = False
    if had_workspace_sign_in_friction:
        await set_login_step_up_pending_after_unlock(db, tenant_id, email_norm)
        mandated_next_sign_in_verification = True
    state_after = await build_sign_in_lock_state(tenant_id, email_norm)

    rid = request.headers.get("X-Request-ID")
    audit_log.info(
        "platform_admin_action=unlock_login tenant_id=%s tenant_slug=%s email_norm=%s "
        "password_fail_streak_rows_deleted=%s rate_limiters=%s mandated_next_sign_in_verification=%s request_id=%s",
        tenant_id,
        tenant.slug,
        email_norm,
        streak_deleted,
        {k: v["had_entries"] for k, v in rate_cleared.items()},
        mandated_next_sign_in_verification,
        rid,
    )

    if mandated_next_sign_in_verification:
        operator_message = (
            "Sign-in limits were cleared for this user. For security, they will need a verification code "
            "the next time they sign in. After that, they can trust the device to skip the code on that browser."
        )
    else:
        operator_message = (
            "No workspace-level sign-in limits were active for this email, so sign-in was already normal. "
            "They will not be asked for an extra email code solely because of this action."
        )

    return {
        "tenant_id": tenant_id,
        "tenant_slug": tenant.slug,
        "email_norm": email_norm,
        "mandated_next_sign_in_verification": mandated_next_sign_in_verification,
        "cleared": {
            "platform_login_password_fail_streaks": {"rows_deleted": streak_deleted},
            "rate_limiters": rate_cleared,
        },
        "state_after": state_after,
        "note": "IP-based login throttle (login_per_ip) is not cleared. If sign-in still shows "
        "a network-wide limit, wait for the window or use another connection.",
        "operator_message": operator_message,
    }
