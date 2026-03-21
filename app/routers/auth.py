from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from app.utils.jwt_auth import TokenType, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.deps.auth import get_current_user, CurrentUser
from app.models.platform import PlatformTenant, PlatformTenantMember, PlatformUser, TenantMembership, UserInvite
from app.routers.me import _account_setup_missing
from app.core.database import get_db
from app.utils.password import verify_password, hash_password
from app.deps.tenant import require_tenant
from app.utils.email import send_password_reset_email
from app.utils.rate_limit import rate_limit_forgot_password
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])
logger = logging.getLogger(__name__)


def _cookie_params(token_type: str) -> dict:
    secure = bool(settings.secure_cookies)
    domain = settings.cookie_domain or (f".{settings.base_domain}" if settings.base_domain else None)
    max_age = settings.jwt_access_minutes * 60 if token_type == TokenType.ACCESS else settings.jwt_refresh_days * 24 * 3600
    base = {
        "httponly": True,
        "secure": secure,
        "samesite": settings.jwt_same_site,
        "domain": domain,
        "max_age": max_age,
    }
    if token_type == TokenType.REFRESH:
        base["path"] = "/api/v1/auth/refresh"
    else:
        base["path"] = "/"
    return base


def _workspace_url(request: Request, slug: str, path_suffix: str = "/dashboard") -> str:
    """
    Build a workspace URL using subdomain pattern: https://{slug}.{base_domain}/{path}
    """
    base_domain = settings.base_domain or request.url.hostname or "localhost"
    scheme = request.url.scheme or "https"
    suffix = path_suffix if path_suffix.startswith("/") else f"/{path_suffix}"
    return f"{scheme}://{slug}.{base_domain}{suffix}"


@router.post("/refresh")
async def refresh(request: Request, response: Response, db=Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    payload = decode_token(token, expected_type=TokenType.REFRESH)
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    tenant_slug = payload.get("tenant_slug")
    roles = payload.get("roles") or []
    if not user_id or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Re-validate user and membership status (block deactivated users from refreshing)
    user = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id)))
    if not user or getattr(user, "status", "ACTIVE") != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    tm = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == int(tenant_id),
            TenantMembership.status == "active",
        ).limit(1)
    )
    if not tm:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    access = create_access_token(user_id=user_id, tenant_id=tenant_id, tenant_slug=tenant_slug, roles=roles)
    new_refresh = create_refresh_token(user_id=user_id, tenant_id=tenant_id, tenant_slug=tenant_slug, roles=roles)

    response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
    response.set_cookie("refresh_token", new_refresh, **_cookie_params(TokenType.REFRESH))
    return {"ok": True}


def _clear_cookie_params(token_type: str) -> dict:
    """Params for clearing a cookie (path/domain must match how it was set)."""
    base = _cookie_params(token_type)
    # Remove max_age so we can set 0; omit domain if None (some servers choke on domain=None)
    out = {
        "path": base["path"],
        "httponly": base["httponly"],
        "secure": base["secure"],
        "samesite": base["samesite"],
        "max_age": 0,
        "expires": 0,
    }
    if base.get("domain") is not None:
        out["domain"] = base["domain"]
    return out


@router.post("/logout")
async def logout(response: Response):
    # Clear auth cookies so no traces remain. Same path/domain as set_cookie so the browser removes them.
    try:
        params_access = _clear_cookie_params(TokenType.ACCESS)
        params_refresh = _clear_cookie_params(TokenType.REFRESH)
        response.set_cookie("access_token", "", **params_access)
        response.set_cookie("refresh_token", "", **params_refresh)
    except Exception:
        # Still return 200 so client can clear local state
        pass
    return {"ok": True}


@router.get("/me")
async def auth_me(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    tenant = current.tenant
    requires_setup, missing_fields, country = _account_setup_missing(tenant)
    company_profile = None
    if tenant and tenant.company_profile:
        p = tenant.company_profile
        company_profile = {
            "legal_name": p.legal_name,
            "address": {
                "street": p.address_street,
                "city": p.address_city,
                "region": p.address_region,
                "postal": p.address_postal,
                "country": p.address_country,
            },
        }
    return {
        "user_id": current.user.id,
        "email": current.user.email,
        "username": getattr(current.user, "username", None) or None,
        "first_name": current.user.first_name or None,
        "last_name": current.user.last_name or None,
        "tenant_id": tenant.id,
        "tenant_slug": tenant.slug,
        "tenant_name": tenant.name,
        "role": current.role,
        "email_verified": bool(getattr(current.user, "is_email_verified", True)),
        "requires_account_setup": requires_setup,
        "account_setup_missing": missing_fields,
        "country_code": country,
        "company_profile": company_profile,
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


RESET_TOKEN_EXPIRY_MINUTES = 60


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    reset_base_url: str | None = None


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db=Depends(get_db)):
    """Request a password reset email. Public (no login). Tenant-aware via host subdomain. When on tenant subdomain, only sends if user is member of that tenant. Always returns 200 with generic message (no enumeration)."""
    ok_msg = {
        "ok": True,
        "sent": True,
        "message": "If an account exists with that email, you will receive a password reset link shortly.",
    }
    try:
        await rate_limit_forgot_password(request, payload.email.strip().lower())
        tenant_id = getattr(request.state, "tenant_id", None)
        user: PlatformUser | None = await db.scalar(
            select(PlatformUser).where(PlatformUser.email == payload.email.strip().lower())
        )
        if not user:
            return ok_msg
        if tenant_id is not None:
            membership = await db.scalar(
                select(PlatformTenantMember).where(
                    PlatformTenantMember.platform_user_id == user.id,
                    PlatformTenantMember.tenant_id == tenant_id,
                ).limit(1)
            )
            if not membership:
                return ok_msg
        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
        user.password_reset_token_hash = token_hash
        user.password_reset_expires_at = expires_at
        await db.commit()
        base = (payload.reset_base_url or "").strip().rstrip("/")
        if not base and settings.base_domain:
            base = f"https://{settings.base_domain}"
        if not base:
            base = "https://truckerp.me"
        reset_link = f"{base}/reset-password?token={raw_token}"
        if not bool(settings.secure_cookies):
            logger.warning("DEV_PASSWORD_RESET_LINK email=%s link=%s", user.email, reset_link)
        try:
            await send_password_reset_email(to=user.email, reset_link=reset_link, expires_minutes=RESET_TOKEN_EXPIRY_MINUTES)
        except Exception as e:
            logger.warning("forgot_password: send_email failed: %s", e)
        return ok_msg
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("forgot_password: error (returning generic 200): %s", e)
        return ok_msg


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=12, max_length=256)


class AcceptInviteRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=12, max_length=256)


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db=Depends(get_db)):
    """Set a new password using the token from the reset email."""
    try:
        token_hash = _hash_reset_token(payload.token)
        now = datetime.now(timezone.utc)
        user: PlatformUser | None = await db.scalar(
            select(PlatformUser).where(
                PlatformUser.password_reset_token_hash == token_hash,
                PlatformUser.password_reset_expires_at > now,
            )
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset link. Please request a new password reset.",
            )
        user.password_hash = hash_password(payload.new_password)
        # Invalidate existing sessions (token refresh should re-check session_version).
        user.session_version = int(getattr(user, "session_version", 1)) + 1
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        await db.commit()
        return {"ok": True, "message": "Your password has been reset. You can now sign in."}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("reset_password: database error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset is temporarily unavailable. Please try again in a few minutes.",
        ) from e
    except Exception as e:
        logger.exception("reset_password: unexpected error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Something went wrong. Please try again later.",
        ) from e


@router.post("/accept-invite")
async def accept_invite(
    payload: AcceptInviteRequest,
    request: Request,
    response: Response,
    tenant_id: int = Depends(require_tenant),
    db=Depends(get_db),
):
    """Set password and activate membership using invite token from email."""
    token_hash = _hash_reset_token(payload.token)
    now = datetime.now(timezone.utc)
    invite = await db.scalar(
        select(UserInvite).where(
            UserInvite.token_hash == token_hash,
            UserInvite.expires_at > now,
            UserInvite.consumed_at.is_(None),
            UserInvite.tenant_id == tenant_id,
        ).limit(1)
    )
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invite link. Ask your admin to send a new invite.",
        )
    user = await db.get(PlatformUser, invite.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite")

    user.password_hash = hash_password(payload.new_password)
    user.session_version = int(getattr(user, "session_version", 1)) + 1
    invite.consumed_at = now

    tm = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == tenant_id,
        ).limit(1)
    )
    if tm:
        tm.status = "active"

    await db.commit()

    tenant = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == tenant_id)
    )
    if tenant:
        membership = await db.scalar(
            select(PlatformTenantMember).where(
                PlatformTenantMember.platform_user_id == user.id,
                PlatformTenantMember.tenant_id == tenant_id,
            ).limit(1)
        )
        roles = [membership.role] if membership and membership.role else []
        access = create_access_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles)
        refresh = create_refresh_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles)
        response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
        response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))

    workspace_url = _workspace_url(request, tenant.slug, "/dashboard") if tenant else None
    return {"ok": True, "message": "Welcome! You can now sign in.", "workspace_url": workspace_url}


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    tenant_id: int = Depends(require_tenant),
    db=Depends(get_db),
):
    email_lower = payload.email.strip().lower()
    user: PlatformUser | None = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_lower))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    membership: PlatformTenantMember | None = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user.id, PlatformTenantMember.tenant_id == tenant_id
        )
    )
    if not membership:
        # Same message as wrong credentials so we don't reveal account exists elsewhere
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # Enforce user account status (ACTIVE = can log in)
    if getattr(user, "status", "ACTIVE") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your workspace admin or support.",
        )

    # Enforce membership gate status (active = can access)
    tm = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == tenant_id,
        ).limit(1)
    )
    if not tm or (tm.status or "").lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this workspace is suspended. Contact your admin.",
        )

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password not set for this account. Use 'Forgot password' to set one.",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    tenant: PlatformTenant | None = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == tenant_id)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if tenant.status != "ACTIVE" or tenant.db_status != "READY":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not ready")

    roles = [membership.role] if membership.role else []
    access = create_access_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles)
    refresh = create_refresh_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles)

    response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
    response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))

    workspace_url = _workspace_url(request, tenant.slug, "/dashboard")
    return {"ok": True, "workspace_url": workspace_url, "access_token": access, "refresh_token": refresh}
