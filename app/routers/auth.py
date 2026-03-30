from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.utils.jwt_auth import TokenType, create_access_token, create_refresh_token, decode_token, extract_sv
from app.core.config import settings
from app.deps.auth import get_current_user, CurrentUser, get_current_platform_user
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import (
    PlatformLoginOtpChallenge,
    PlatformTenant,
    PlatformTenantMember,
    PlatformUser,
    TenantMembership,
    TenantStatus,
    UserInvite,
    PlatformTenantUserMap,
)
from app.models.tenant_auth import TenantUser, TenantUserInvite, TenantWorkspaceMember
from app.routers.me import _account_setup_missing
from app.core.database import get_db
from app.utils.auth_identity import normalize_auth_email
from app.utils.password import verify_password, hash_password
from app.deps.tenant import require_tenant
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
from app.services.tenant_auth_dual_write import (
    apply_password_and_session_version_platform_primary,
    apply_password_and_session_version_tenant_primary,
    mirror_reset_tokens_to_platform,
    mirror_reset_tokens_to_tenant,
    mirror_tenant_user_credentials_to_platform,
)
from app.utils.email import send_password_reset_email
from app.utils.rate_limit import (
    check_create_workspace_rate_limits,
    rate_limit_forgot_password,
    rate_limit_login_ip,
    rate_limit_login_tenant_email,
    rate_limit_login_step_up_issue,
    rate_limit_login_step_up_verify,
)
from app.utils.slug import is_slug_available
from app.schemas.signup import CreateWorkspaceRequest, VerifyOTPResponse, _normalize_phone_digits
from app.services.workspace_bootstrap import provision_new_workspace_for_platform_user
from app.services.login_failure_audit import (
    LOGIN_FAIL_APEX_NO_PLATFORM_TENANT,
    LOGIN_FAIL_NO_PLATFORM_MEMBERSHIP,
    LOGIN_FAIL_NO_PLATFORM_USER,
    LOGIN_FAIL_NO_TENANT_USER,
    LOGIN_FAIL_NO_WORKSPACE_MEMBER,
    LOGIN_FAIL_TENANT_AUTH_INCOMPLETE,
    LOGIN_FAIL_VERIFY_PLATFORM_PASSWORD,
    LOGIN_FAIL_VERIFY_TENANT_PASSWORD,
    log_and_persist_login_failure,
)
from app.services.login_password_abuse import (
    assert_login_human_verification_if_armed,
    clear_login_password_fail_streak,
    record_login_password_verify_failure,
)
from app.services.login_step_up_otp import (
    issue_login_step_up_otp_for_challenge,
    login_step_up_challenge_gate_after_password,
    verify_login_step_up_otp_for_challenge,
)
from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field

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
    sv = extract_sv(payload)
    if sv is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    tenant_row = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))
    if not tenant_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    mode = getattr(tenant_row, "tenant_auth_mode", None) or "platform"

    if tenant_uses_tenant_db_auth(mode):
        try:
            tu_id = int(str(user_id))
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
        sub: int | None = None
        sv_out: int | None = None
        roles_for_tokens: list = []
        async for tdb in open_tenant_session_by_id(int(tenant_id)):
            tu = await tdb.scalar(
                select(TenantUser).where(TenantUser.tenant_id == int(tenant_id), TenantUser.id == tu_id)
            )
            if not tu or (tu.status or "").upper() != "ACTIVE":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
            if int(getattr(tu, "session_version", 1) or 1) != int(sv):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
            twm = await tdb.scalar(
                select(TenantWorkspaceMember).where(
                    TenantWorkspaceMember.tenant_id == int(tenant_id),
                    TenantWorkspaceMember.tenant_user_id == tu_id,
                    TenantWorkspaceMember.status == "active",
                )
            )
            if not twm:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
            roles_for_tokens = [twm.role] if twm.role else []
            sub = tu.id
            sv_out = int(tu.session_version)
            break

        if sub is None or sv_out is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
        access = create_access_token(
            user_id=sub, tenant_id=int(tenant_id), tenant_slug=tenant_slug, roles=roles_for_tokens, sv=sv_out
        )
        new_refresh = create_refresh_token(
            user_id=sub, tenant_id=int(tenant_id), tenant_slug=tenant_slug, roles=roles_for_tokens, sv=sv_out
        )
    else:
        user = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id)))
        if not user or getattr(user, "status", "ACTIVE") != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
        if int(getattr(user, "session_version", 1) or 1) != int(sv):
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
        sv_out = int(user.session_version)
        access = create_access_token(
            user_id=user.id, tenant_id=tenant_id, tenant_slug=tenant_slug, roles=roles, sv=sv_out
        )
        new_refresh = create_refresh_token(
            user_id=user.id, tenant_id=tenant_id, tenant_slug=tenant_slug, roles=roles, sv=sv_out
        )

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
    out = {
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
        "tenant_auth_mode": getattr(tenant, "tenant_auth_mode", None) or "platform",
    }
    if current.tenant_user is not None:
        out["tenant_local_user_id"] = int(current.tenant_user.id)
    return out


class LoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    password: str
    turnstile_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("turnstile_token", "cf_turnstile_response", "cf-turnstile-response"),
    )
    login_challenge_id: str | None = None


class LoginStepUpIssueRequest(BaseModel):
    login_challenge_id: str = Field(..., min_length=36, max_length=36)


class LoginStepUpVerifyRequest(BaseModel):
    login_challenge_id: str = Field(..., min_length=36, max_length=36)
    otp: str = Field(..., min_length=4, max_length=32)


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
        email_norm = normalize_auth_email(payload.email)
        await rate_limit_forgot_password(request, email_norm)
        tenant_id = getattr(request.state, "tenant_id", None)
        tenant_row = None
        if tenant_id is not None:
            tenant_row = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))

        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
        user: PlatformUser | None = None

        if (
            tenant_row
            and tenant_id is not None
            and tenant_uses_tenant_db_auth(getattr(tenant_row, "tenant_auth_mode", None))
        ):
            async for tdb in open_tenant_session_by_id(int(tenant_id)):
                tu = await tdb.scalar(
                    select(TenantUser).where(
                        TenantUser.tenant_id == int(tenant_id),
                        TenantUser.email_norm == email_norm,
                    )
                )
                if not tu:
                    return ok_msg
                twm_any = await tdb.scalar(
                    select(TenantWorkspaceMember).where(
                        TenantWorkspaceMember.tenant_id == int(tenant_id),
                        TenantWorkspaceMember.tenant_user_id == tu.id,
                    )
                )
                if not twm_any:
                    return ok_msg
                tu.password_reset_token_hash = token_hash
                tu.password_reset_expires_at = expires_at
                await tdb.commit()
                pmap = await db.scalar(
                    select(PlatformTenantUserMap).where(
                        PlatformTenantUserMap.tenant_id == int(tenant_id),
                        PlatformTenantUserMap.tenant_user_id == int(tu.id),
                    )
                )
                if not pmap:
                    logger.critical(
                        "forgot_password missing map tenant_id=%s tenant_user_id=%s",
                        tenant_id,
                        tu.id,
                    )
                    raise RuntimeError("dual_write_missing_map")
                await mirror_reset_tokens_to_platform(
                    platform_db=db,
                    platform_user_id=str(pmap.platform_user_id),
                    token_hash=token_hash,
                    expires_at=expires_at,
                )
                user = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(pmap.platform_user_id)))
                break
        else:
            user = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
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
            user.password_reset_token_hash = token_hash
            user.password_reset_expires_at = expires_at
            await db.commit()
            if tenant_id is not None:
                pmap2 = await db.scalar(
                    select(PlatformTenantUserMap).where(
                        PlatformTenantUserMap.tenant_id == int(tenant_id),
                        PlatformTenantUserMap.platform_user_id == str(user.id),
                    )
                )
                if pmap2:
                    try:
                        async for tdb in open_tenant_session_by_id(int(tenant_id)):
                            await mirror_reset_tokens_to_tenant(
                                tenant_db=tdb,
                                tenant_id=int(tenant_id),
                                tenant_user_id=int(pmap2.tenant_user_id),
                                token_hash=token_hash,
                                expires_at=expires_at,
                            )
                    except Exception:
                        logger.critical(
                            "forgot_password dual_write tenant failed platform_user_id=%s",
                            user.id,
                        )
                        raise

        if not user:
            return ok_msg

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
async def reset_password(payload: ResetPasswordRequest, request: Request, db=Depends(get_db)):
    """Set a new password using the token from the reset email."""
    try:
        token_hash = _hash_reset_token(payload.token)
        now = datetime.now(timezone.utc)
        tenant_id = getattr(request.state, "tenant_id", None)
        tenant_row = None
        if tenant_id is not None:
            tenant_row = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))

        if (
            tenant_row
            and tenant_id is not None
            and tenant_uses_tenant_db_auth(getattr(tenant_row, "tenant_auth_mode", None))
        ):
            async for tdb in open_tenant_session_by_id(int(tenant_id)):
                tu = await tdb.scalar(
                    select(TenantUser).where(
                        TenantUser.tenant_id == int(tenant_id),
                        TenantUser.password_reset_token_hash == token_hash,
                        TenantUser.password_reset_expires_at > now,
                    )
                )
                if tu:
                    await apply_password_and_session_version_tenant_primary(
                        platform_db=db,
                        tenant_db=tdb,
                        tenant_id=int(tenant_id),
                        tenant_user=tu,
                        new_password_plain=payload.new_password,
                        bump_session=True,
                    )
                    return {"ok": True, "message": "Your password has been reset. You can now sign in."}
                break

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
        mode = getattr(tenant_row, "tenant_auth_mode", None) or "platform" if tenant_row else "platform"
        tid = int(tenant_id) if tenant_id is not None else None
        if tid is not None:
            async for tdb in open_tenant_session_by_id(tid):
                await apply_password_and_session_version_platform_primary(
                    platform_db=db,
                    tenant_db=tdb,
                    tenant_id=tid,
                    platform_user=user,
                    tenant_auth_mode=mode,
                    new_password_plain=payload.new_password,
                    bump_session=True,
                )
                break
        else:
            user.password_hash = hash_password(payload.new_password)
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
    tenant = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == tenant_id)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    if tenant_uses_tenant_db_auth(getattr(tenant, "tenant_auth_mode", None)):
        sub: int | None = None
        sv_out: int | None = None
        roles: list = []
        async for tdb in open_tenant_session_by_id(int(tenant_id)):
            tinv = await tdb.scalar(
                select(TenantUserInvite).where(
                    TenantUserInvite.token_hash == token_hash,
                    TenantUserInvite.tenant_id == int(tenant_id),
                    TenantUserInvite.expires_at > now,
                    TenantUserInvite.consumed_at.is_(None),
                )
            )
            if not tinv:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired invite link. Ask your admin to send a new invite.",
                )
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == int(tenant_id), TenantUser.id == tinv.tenant_user_id
                )
            )
            if not tu:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite")
            twm = await tdb.scalar(
                select(TenantWorkspaceMember).where(
                    TenantWorkspaceMember.tenant_id == int(tenant_id),
                    TenantWorkspaceMember.tenant_user_id == tu.id,
                )
            )
            if not twm:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite")
            await apply_password_and_session_version_tenant_primary(
                platform_db=db,
                tenant_db=tdb,
                tenant_id=int(tenant_id),
                tenant_user=tu,
                new_password_plain=payload.new_password,
                bump_session=True,
                defer_tenant_commit=True,
            )
            tinv.consumed_at = now
            twm.status = "active"
            await tdb.commit()
            await tdb.refresh(tu)
            await mirror_tenant_user_credentials_to_platform(
                platform_db=db,
                tenant_id=int(tenant_id),
                tenant_user=tu,
                mirror_password=True,
                mirror_session=True,
            )
            pmap = await db.scalar(
                select(PlatformTenantUserMap).where(
                    PlatformTenantUserMap.tenant_id == int(tenant_id),
                    PlatformTenantUserMap.tenant_user_id == tu.id,
                )
            )
            if not pmap:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Account mapping incomplete")
            user = await db.get(PlatformUser, pmap.platform_user_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite")
            pinv = await db.scalar(
                select(UserInvite).where(
                    UserInvite.token_hash == token_hash,
                    UserInvite.tenant_id == int(tenant_id),
                    UserInvite.consumed_at.is_(None),
                )
            )
            if pinv:
                pinv.consumed_at = now
            tm = await db.scalar(
                select(TenantMembership).where(
                    TenantMembership.user_id == user.id,
                    TenantMembership.tenant_id == int(tenant_id),
                )
            )
            if tm:
                tm.status = "active"
            await db.commit()
            roles = [twm.role] if twm and twm.role else []
            sv_out = int(tu.session_version)
            sub = tu.id
            break

        if sub is None or sv_out is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Invite acceptance could not be completed. Please try again or contact support.",
            )
        access = create_access_token(
            user_id=sub, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out
        )
        refresh = create_refresh_token(
            user_id=sub, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out
        )
        response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
        response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))
        workspace_url = _workspace_url(request, tenant.slug, "/dashboard")
        return {"ok": True, "message": "Welcome! You can now sign in.", "workspace_url": workspace_url}

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

    invite.consumed_at = now
    tm = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == tenant_id,
        ).limit(1)
    )
    if tm:
        tm.status = "active"

    mode = getattr(tenant, "tenant_auth_mode", None) or "platform"
    async for tdb in open_tenant_session_by_id(int(tenant_id)):
        await apply_password_and_session_version_platform_primary(
            platform_db=db,
            tenant_db=tdb,
            tenant_id=int(tenant_id),
            platform_user=user,
            tenant_auth_mode=mode,
            new_password_plain=payload.new_password,
            bump_session=True,
        )
        break

    membership = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user.id,
            PlatformTenantMember.tenant_id == tenant_id,
        ).limit(1)
    )
    roles = [membership.role] if membership and membership.role else []
    user = await db.scalar(select(PlatformUser).where(PlatformUser.id == user.id))
    sv_out = int(getattr(user, "session_version", 1) or 1)
    access = create_access_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out)
    refresh = create_refresh_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out)
    response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
    response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))

    workspace_url = _workspace_url(request, tenant.slug, "/dashboard")
    return {"ok": True, "message": "Welcome! You can now sign in.", "workspace_url": workspace_url}


async def _resolve_tenant_id_for_apex_login(request: Request, db, payload: LoginRequest) -> int:
    """
    When the browser is on the marketing host (no workspace subdomain), resolve which tenant this
    login targets using email + password and platform/tenant credentials (same rules as subdomain login).
    """
    email_norm = normalize_auth_email(payload.email)
    user = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if getattr(user, "status", "ACTIVE") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your workspace admin or support.",
        )

    q = (
        select(TenantMembership, PlatformTenant)
        .join(PlatformTenant, PlatformTenant.id == TenantMembership.tenant_id)
        .where(
            TenantMembership.user_id == user.id,
            TenantMembership.status == "active",
            PlatformTenant.status == "ACTIVE",
            PlatformTenant.db_status == "READY",
        )
        .order_by(PlatformTenant.id)
    )
    rows = (await db.execute(q)).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    for _tm, tenant in rows:
        tid = int(tenant.id)
        if not tenant_uses_tenant_db_auth(getattr(tenant, "tenant_auth_mode", None)):
            continue
        async for tdb in open_tenant_session_by_id(tid):
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == tid,
                    TenantUser.email_norm == email_norm,
                )
            )
            if not tu or (tu.status or "").upper() != "ACTIVE":
                break
            twm = await tdb.scalar(
                select(TenantWorkspaceMember).where(
                    TenantWorkspaceMember.tenant_id == tid,
                    TenantWorkspaceMember.tenant_user_id == tu.id,
                    TenantWorkspaceMember.status == "active",
                )
            )
            if not twm:
                break
            if not tu.password_hash:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Password not set for this account. Use 'Forgot password' to set one.",
                )
            await assert_login_human_verification_if_armed(tid, email_norm, payload.turnstile_token)
            if not verify_password(payload.password, tu.password_hash):
                await record_login_password_verify_failure(tid, email_norm)
                pt_row = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == tid))
                if pt_row:
                    await log_and_persist_login_failure(
                        request=request,
                        tenant_id=tid,
                        tenant_slug=pt_row.slug,
                        tenant_auth_mode=(getattr(pt_row, "tenant_auth_mode", None) or "tenant"),
                        email_norm=email_norm,
                        reason_code=LOGIN_FAIL_VERIFY_TENANT_PASSWORD,
                    )
                break
            pmap = await db.scalar(
                select(PlatformTenantUserMap).where(
                    PlatformTenantUserMap.tenant_id == tid,
                    PlatformTenantUserMap.tenant_user_id == tu.id,
                )
            )
            if pmap and str(pmap.platform_user_id) == str(user.id):
                return tid
            break

    platform_tenant_ids: list[int] = [
        int(t.id)
        for _tm, t in rows
        if not tenant_uses_tenant_db_auth(getattr(t, "tenant_auth_mode", None))
    ]
    if not platform_tenant_ids:
        t0 = rows[0][1]
        await log_and_persist_login_failure(
            request=request,
            tenant_id=int(t0.id),
            tenant_slug=t0.slug,
            tenant_auth_mode=(getattr(t0, "tenant_auth_mode", None) or "platform"),
            email_norm=email_norm,
            reason_code=LOGIN_FAIL_APEX_NO_PLATFORM_TENANT,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password not set for this account. Use 'Forgot password' to set one.",
        )
    tid_pf = platform_tenant_ids[0]
    await assert_login_human_verification_if_armed(tid_pf, email_norm, payload.turnstile_token)
    if not verify_password(payload.password, user.password_hash):
        await record_login_password_verify_failure(tid_pf, email_norm)
        pt = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == tid_pf))
        if pt:
            await log_and_persist_login_failure(
                request=request,
                tenant_id=tid_pf,
                tenant_slug=pt.slug,
                tenant_auth_mode=(getattr(pt, "tenant_auth_mode", None) or "platform"),
                email_norm=email_norm,
                reason_code=LOGIN_FAIL_VERIFY_PLATFORM_PASSWORD,
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if len(platform_tenant_ids) > 1:
        base = (settings.base_domain or "example.com").lower()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This account is in more than one workspace. Sign in using your company's web address, "
                f"for example https://your-workspace.{base}/login"
            ),
        )
    return platform_tenant_ids[0]


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db=Depends(get_db),
):
    await rate_limit_login_ip(request)
    email_norm = normalize_auth_email(payload.email)
    tenant_id_ctx = getattr(request.state, "tenant_id", None)
    if tenant_id_ctx is None:
        tenant_id = await _resolve_tenant_id_for_apex_login(request, db, payload)
        request.state.tenant_id = tenant_id
        t_slug_row = await db.scalar(select(PlatformTenant.slug).where(PlatformTenant.id == int(tenant_id)))
        if t_slug_row:
            request.state.tenant_slug = str(t_slug_row)
    else:
        tenant_id = int(tenant_id_ctx)
    await rate_limit_login_tenant_email(request, tenant_id, email_norm)
    tenant: PlatformTenant | None = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == tenant_id)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if tenant.status != "ACTIVE" or tenant.db_status != "READY":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not ready")

    if tenant_uses_tenant_db_auth(getattr(tenant, "tenant_auth_mode", None)):
        sub: int | None = None
        sv_out: int | None = None
        roles: list = []
        async for tdb in open_tenant_session_by_id(int(tenant_id)):
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == int(tenant_id),
                    TenantUser.email_norm == email_norm,
                )
            )
            if not tu:
                await log_and_persist_login_failure(
                    request=request,
                    tenant_id=tenant_id,
                    tenant_slug=tenant.slug,
                    tenant_auth_mode="tenant",
                    email_norm=email_norm,
                    reason_code=LOGIN_FAIL_NO_TENANT_USER,
                )
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
            if (tu.status or "").upper() != "ACTIVE":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is deactivated. Contact your workspace admin or support.",
                )
            twm = await tdb.scalar(
                select(TenantWorkspaceMember).where(
                    TenantWorkspaceMember.tenant_id == int(tenant_id),
                    TenantWorkspaceMember.tenant_user_id == tu.id,
                    TenantWorkspaceMember.status == "active",
                )
            )
            if not twm:
                await log_and_persist_login_failure(
                    request=request,
                    tenant_id=tenant_id,
                    tenant_slug=tenant.slug,
                    tenant_auth_mode="tenant",
                    email_norm=email_norm,
                    reason_code=LOGIN_FAIL_NO_WORKSPACE_MEMBER,
                )
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
            if not tu.password_hash:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Password not set for this account. Use 'Forgot password' to set one.",
                )
            await assert_login_human_verification_if_armed(tenant_id, email_norm, payload.turnstile_token)
            if not verify_password(payload.password, tu.password_hash):
                await record_login_password_verify_failure(tenant_id, email_norm)
                await log_and_persist_login_failure(
                    request=request,
                    tenant_id=tenant_id,
                    tenant_slug=tenant.slug,
                    tenant_auth_mode="tenant",
                    email_norm=email_norm,
                    reason_code=LOGIN_FAIL_VERIFY_TENANT_PASSWORD,
                )
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

            pmap = await db.scalar(
                select(PlatformTenantUserMap).where(
                    PlatformTenantUserMap.tenant_id == int(tenant_id),
                    PlatformTenantUserMap.tenant_user_id == tu.id,
                )
            )
            if not pmap:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Account mapping incomplete; contact support.",
                )
            user: PlatformUser | None = await db.scalar(
                select(PlatformUser).where(PlatformUser.id == str(pmap.platform_user_id))
            )
            if not user or getattr(user, "status", "ACTIVE") != "ACTIVE":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is deactivated. Contact your workspace admin or support.",
                )
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
            gate = await login_step_up_challenge_gate_after_password(
                db,
                tenant_id=tenant_id,
                email_norm=email_norm,
                login_challenge_id=payload.login_challenge_id,
            )
            if gate is not None:
                return gate
            roles = [twm.role] if twm.role else []
            sv_out = int(getattr(tu, "session_version", 1) or 1)
            sub = tu.id
            break

        if sub is None or sv_out is None:
            await log_and_persist_login_failure(
                request=request,
                tenant_id=tenant_id,
                tenant_slug=tenant.slug,
                tenant_auth_mode="tenant",
                email_norm=email_norm,
                reason_code=LOGIN_FAIL_TENANT_AUTH_INCOMPLETE,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        await clear_login_password_fail_streak(tenant_id, email_norm)
        access = create_access_token(
            user_id=sub, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out
        )
        refresh = create_refresh_token(
            user_id=sub, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out
        )
        response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
        response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))
        workspace_url = _workspace_url(request, tenant.slug, "/dashboard")
        return {"ok": True, "workspace_url": workspace_url, "access_token": access, "refresh_token": refresh}

    user = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
    if not user:
        await log_and_persist_login_failure(
            request=request,
            tenant_id=tenant_id,
            tenant_slug=tenant.slug,
            tenant_auth_mode=(getattr(tenant, "tenant_auth_mode", None) or "platform"),
            email_norm=email_norm,
            reason_code=LOGIN_FAIL_NO_PLATFORM_USER,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    membership: PlatformTenantMember | None = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user.id, PlatformTenantMember.tenant_id == tenant_id
        )
    )
    if not membership:
        await log_and_persist_login_failure(
            request=request,
            tenant_id=tenant_id,
            tenant_slug=tenant.slug,
            tenant_auth_mode=(getattr(tenant, "tenant_auth_mode", None) or "platform"),
            email_norm=email_norm,
            reason_code=LOGIN_FAIL_NO_PLATFORM_MEMBERSHIP,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if getattr(user, "status", "ACTIVE") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your workspace admin or support.",
        )

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
    await assert_login_human_verification_if_armed(tenant_id, email_norm, payload.turnstile_token)
    if not verify_password(payload.password, user.password_hash):
        await record_login_password_verify_failure(tenant_id, email_norm)
        await log_and_persist_login_failure(
            request=request,
            tenant_id=tenant_id,
            tenant_slug=tenant.slug,
            tenant_auth_mode=(getattr(tenant, "tenant_auth_mode", None) or "platform"),
            email_norm=email_norm,
            reason_code=LOGIN_FAIL_VERIFY_PLATFORM_PASSWORD,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    gate_pf = await login_step_up_challenge_gate_after_password(
        db,
        tenant_id=tenant_id,
        email_norm=email_norm,
        login_challenge_id=payload.login_challenge_id,
    )
    if gate_pf is not None:
        return gate_pf

    roles = [membership.role] if membership.role else []
    sv_out = int(getattr(user, "session_version", 1) or 1)
    access = create_access_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out)
    refresh = create_refresh_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles, sv=sv_out)

    response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
    response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))

    await clear_login_password_fail_streak(tenant_id, email_norm)
    workspace_url = _workspace_url(request, tenant.slug, "/dashboard")
    return {"ok": True, "workspace_url": workspace_url, "access_token": access, "refresh_token": refresh}


@router.post("/login-step-up/issue")
async def login_step_up_issue(
    payload: LoginStepUpIssueRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Issue login step-up OTP for an active login_challenge_id on this workspace Host. Uniform success body.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    ch = await db.scalar(
        select(PlatformLoginOtpChallenge).where(
            PlatformLoginOtpChallenge.id == payload.login_challenge_id.strip(),
            PlatformLoginOtpChallenge.tenant_id == int(tenant_id),
        )
    )
    email_for_rl = ch.email_norm if ch is not None else payload.login_challenge_id.strip()
    await rate_limit_login_step_up_issue(request, int(tenant_id), email_for_rl)
    await issue_login_step_up_otp_for_challenge(
        db=db,
        request=request,
        tenant_id=int(tenant_id),
        login_challenge_id=payload.login_challenge_id.strip(),
    )
    return {
        "ok": True,
        "message": "If an account exists for this workspace, you will receive a code shortly.",
    }


@router.post("/login-step-up/verify")
async def login_step_up_verify(
    payload: LoginStepUpVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Verify login step-up OTP for login_challenge_id on this workspace Host."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    ch = await db.scalar(
        select(PlatformLoginOtpChallenge).where(
            PlatformLoginOtpChallenge.id == payload.login_challenge_id.strip(),
            PlatformLoginOtpChallenge.tenant_id == int(tenant_id),
        )
    )
    email_for_rl = ch.email_norm if ch is not None else payload.login_challenge_id.strip()
    await rate_limit_login_step_up_verify(request, int(tenant_id), email_for_rl)
    ok = await verify_login_step_up_otp_for_challenge(
        db=db,
        request=request,
        tenant_id=int(tenant_id),
        login_challenge_id=payload.login_challenge_id.strip(),
        otp_code=payload.otp.strip(),
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return {"ok": True}


@router.post("/workspaces", response_model=VerifyOTPResponse)
async def create_workspace(
    payload: CreateWorkspaceRequest,
    request: Request,
    response: Response,
    user: PlatformUser = Depends(get_current_platform_user),
    db=Depends(get_db),
):
    """
    Authenticated user creates an additional workspace (new platform tenant + provision + seed).
    Uses platform DB + provisioning only; does not read or mutate other tenants' business data.
    """
    check_create_workspace_rate_limits(request, str(user.id))

    normalized_slug = payload.workspace_slug
    if not await is_slug_available(db, normalized_slug):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug is not available")

    user.first_name = payload.first_name.strip()
    user.last_name = payload.last_name.strip()
    digits = _normalize_phone_digits(payload.phone)
    if digits:
        user.phone = f"+{digits}"

    now = datetime.now(timezone.utc)
    country = payload.address.country.strip().upper()
    try:
        tenant, membership = await provision_new_workspace_for_platform_user(
            db,
            user=user,
            normalized_slug=normalized_slug,
            tenant_display_name=payload.company_legal_name.strip(),
            country_code=country,
            creator_first_name=payload.first_name.strip(),
            creator_last_name=payload.last_name.strip(),
            now=now,
            onboarding_draft=None,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.exception("create_workspace integrity_error user_id=%s slug=%s", user.id, normalized_slug)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create workspace. Try a different slug.",
        ) from None
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("create_workspace failed user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workspace creation failed",
        ) from exc

    requires_company_setup = tenant.status == TenantStatus.PENDING_SETUP.value
    workspace_url = _workspace_url(
        request,
        tenant.slug,
        "/company-setup" if requires_company_setup else "/",
    )

    await db.refresh(user)
    sv_tok = int(getattr(user, "session_version", 1) or 1)
    access = create_access_token(
        user_id=user.id,
        tenant_id=int(tenant.id),
        tenant_slug=tenant.slug,
        roles=[membership.role],
        sv=sv_tok,
    )
    refresh = create_refresh_token(
        user_id=user.id,
        tenant_id=int(tenant.id),
        tenant_slug=tenant.slug,
        roles=[membership.role],
        sv=sv_tok,
    )
    response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
    response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))

    return VerifyOTPResponse(
        message="Workspace created.",
        verified=True,
        requires_company_setup=requires_company_setup,
        workspace_url=workspace_url,
        tenant_id=int(tenant.id),
        slug=tenant.slug,
    )
