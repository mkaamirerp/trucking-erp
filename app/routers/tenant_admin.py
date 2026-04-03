"""Tenant Admin / Configuration API. Company-level setup and control.
Platform admin = SaaS control plane. Tenant admin = one company managing its own profile, settings, etc.

Business documents (invoices, pay stubs) must use canonical company profile only.
Admin UI may show fallback (owner/payload) for display safety; completeness flags
indicate when document-facing data is ready.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps.admin import access_level_to_role, has_full_access, is_tenant_admin, role_to_access_level
from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import (
    PlatformCompanyProfile,
    PlatformTenant,
    PlatformTenantMember,
    PlatformTenantUserMap,
    PlatformUser,
    TenantMembership,
    UserInvite,
)
from app.models.tenant_auth import TenantUser, TenantUserInvite, TenantWorkspaceMember
from app.services.login_password_abuse import clear_login_password_fail_streak
from app.services.login_unlock_step_up_pending import set_login_step_up_pending_after_unlock
from app.services.sign_in_lock_state import build_sign_in_lock_state, build_sign_in_security_panel
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
from app.utils.auth_identity import normalize_auth_email
from app.utils.rate_limit import clear_login_unlock_throttles_for_tenant_email
from app.utils.email import send_user_invite_email
from app.utils.password import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Tenant Admin"],
    dependencies=[Depends(require_entitlement("admin_sensitive"))],
)


class CompanyProfileOut(BaseModel):
    """Frontend-safe company profile DTO. Includes completeness and fallback signals."""

    tenant_name: str
    slug: str
    timezone: str
    base_currency: str
    country_code: str | None
    legal_name: str | None = None
    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal: str | None = None
    country: str | None = None
    company_phone: str | None = None
    company_email: str | None = None
    usdot_number: str | None = None
    mc_number: str | None = None
    cvor_number: str | None = None
    operator_license: str | None = None
    hst_number: str | None = None
    has_w9_file: bool = False
    setup_completed_at: str | None = None
    # Completeness flags: true only when canonical profile has the data
    has_business_address: bool = False
    has_company_phone: bool = False
    has_company_email: bool = False
    is_document_contact_complete: bool = False
    # Fallback indicators: true when displayed value comes from owner/payload, not profile
    company_phone_is_fallback: bool = False
    company_email_is_fallback: bool = False
    address_is_fallback: bool = False


def _has_full_address(addr: dict) -> bool:
    if not addr or not isinstance(addr, dict):
        return False
    required = ("street", "city", "region", "postal", "country")
    return all(addr.get(k) for k in required)


def _canonical_completeness(profile: PlatformCompanyProfile | None) -> tuple[bool, bool, bool, bool]:
    """Returns (has_address, has_phone, has_email, is_document_ready)."""
    if not profile:
        return False, False, False, False
    has_addr = all(
        bool((getattr(profile, f"address_{k}", None) or "").strip())
        for k in ("street", "city", "region", "postal", "country")
    )
    has_phone = bool((profile.company_phone or "").strip())
    has_email = bool((profile.company_email or "").strip())
    has_legal = bool((profile.legal_name or "").strip())
    doc_ready = has_legal and has_addr and has_phone and has_email
    return has_addr, has_phone, has_email, doc_ready


@router.get("/company-profile", response_model=CompanyProfileOut)
async def get_company_profile(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant company profile. Canonical from platform_company_profiles; fallback for admin UI only."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")

    tenant = await db.scalar(
        select(PlatformTenant)
        .options(
            selectinload(PlatformTenant.company_profile),
            selectinload(PlatformTenant.onboarding_payload),
            selectinload(PlatformTenant.members).selectinload(PlatformTenantMember.platform_user),
        )
        .where(PlatformTenant.id == tenant_id)
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    profile: PlatformCompanyProfile | None = tenant.company_profile
    payload_for_fallback = None

    # Repair: if profile missing but payload has full address, create profile from payload
    if profile is None and tenant.onboarding_payload and tenant.onboarding_payload.payload_json:
        pj = tenant.onboarding_payload.payload_json
        addr = pj.get("address") or {}
        if _has_full_address(addr):
            legal = (pj.get("company_legal_name") or tenant.name or "").strip() or tenant.name
            profile = PlatformCompanyProfile(
                tenant_id=tenant_id,
                legal_name=legal,
                address_street=(addr.get("street") or "").strip() or "",
                address_city=(addr.get("city") or "").strip() or "",
                address_region=(addr.get("region") or "").strip() or "",
                address_postal=(addr.get("postal") or "").strip() or "",
                address_country=(addr.get("country") or "").strip().upper() or "US",
                company_phone=(pj.get("phone") or "").strip() or None,
                company_email=(pj.get("email") or "").strip().lower() or None,
                setup_completed_at=None,
            )
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
        else:
            payload_for_fallback = pj
    elif profile is None and tenant.onboarding_payload and tenant.onboarding_payload.payload_json:
        payload_for_fallback = tenant.onboarding_payload.payload_json

    # Canonical: from profile only (never owner or payload)
    canonical_phone = (profile.company_phone or "").strip() or None if profile else None
    canonical_email = (profile.company_email or "").strip().lower() or None if profile else None
    has_addr, has_phone, has_email, doc_ready = _canonical_completeness(profile)

    # Fallback: for admin UI display only (owner or payload)
    display_phone = canonical_phone
    display_email = canonical_email
    phone_is_fallback = False
    email_is_fallback = False
    address_is_fallback = False

    if not canonical_phone or not canonical_email or (profile is None and payload_for_fallback):
        owner = next(
            (m.platform_user for m in (tenant.members or []) if m.role in ("TENANT_OWNER", "TENANT_ADMIN")),
            None,
        )
        if not canonical_phone:
            display_phone = owner.phone if owner else (payload_for_fallback or {}).get("phone") or None
            phone_is_fallback = bool(display_phone)
        if not canonical_email:
            display_email = owner.email if owner else (payload_for_fallback or {}).get("email") or None
            email_is_fallback = bool(display_email)

    # Address: canonical from profile, or fallback from payload
    if profile:
        legal_name = profile.legal_name
        street = profile.address_street
        city = profile.address_city
        region = profile.address_region
        postal = profile.address_postal
        country = profile.address_country
        address_is_fallback = False
    elif payload_for_fallback:
        addr = payload_for_fallback.get("address") or {}
        legal_name = (payload_for_fallback.get("company_legal_name") or tenant.name or "").strip() or None
        street = (addr.get("street") or "").strip() or None
        city = (addr.get("city") or "").strip() or None
        region = (addr.get("region") or "").strip() or None
        postal = (addr.get("postal") or "").strip() or None
        country = (addr.get("country") or "").strip().upper() or None
        address_is_fallback = bool(street or city or region or postal or country)
    else:
        legal_name = street = city = region = postal = country = None

    return CompanyProfileOut(
        tenant_name=tenant.name,
        slug=tenant.slug,
        timezone=tenant.timezone or "America/Toronto",
        base_currency=tenant.base_currency or "USD",
        country_code=tenant.country_code,
        legal_name=legal_name,
        street=street,
        city=city,
        region=region,
        postal=postal,
        country=country,
        company_phone=display_phone,
        company_email=display_email,
        usdot_number=profile.usdot_number if profile else None,
        mc_number=profile.mc_number if profile else None,
        cvor_number=profile.cvor_number if profile else None,
        operator_license=profile.operator_license if profile else None,
        hst_number=profile.hst_number if profile else None,
        has_w9_file=bool(profile and profile.w9_storage_key),
        setup_completed_at=(
            profile.setup_completed_at.isoformat() if profile and profile.setup_completed_at else None
        ),
        has_business_address=has_addr,
        has_company_phone=has_phone,
        has_company_email=has_email,
        is_document_contact_complete=doc_ready,
        company_phone_is_fallback=phone_is_fallback,
        company_email_is_fallback=email_is_fallback,
        address_is_fallback=address_is_fallback,
    )


# ---- Tenant users (list, invite, suspend, reactivate) ----


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


INVITE_EXPIRY_HOURS = 24


async def _perform_invite_resend(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant: PlatformTenant,
    user: PlatformUser,
    inviter_user_id: str,
    request: Request,
) -> dict:
    """Invalidate unconsumed invites for this user+tenant, create a new token, send email, commit."""
    now = datetime.now(timezone.utc)
    stale_invites = (
        await db.scalars(
            select(UserInvite).where(
                UserInvite.user_id == user.id,
                UserInvite.tenant_id == tenant_id,
                UserInvite.consumed_at.is_(None),
            )
        )
    ).all()
    for inv in stale_invites:
        inv.consumed_at = now
    await db.flush()

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = now + timedelta(hours=INVITE_EXPIRY_HOURS)

    if tenant_uses_tenant_db_auth(getattr(tenant, "tenant_auth_mode", None)):
        pmap_u = await db.scalar(
            select(PlatformTenantUserMap).where(
                PlatformTenantUserMap.tenant_id == int(tenant_id),
                PlatformTenantUserMap.platform_user_id == str(user.id),
            )
        )
        if pmap_u:
            async for tdb in open_tenant_session_by_id(int(tenant_id)):
                _ti_res = await tdb.execute(
                    select(TenantUserInvite).where(
                        TenantUserInvite.tenant_id == int(tenant_id),
                        TenantUserInvite.tenant_user_id == int(pmap_u.tenant_user_id),
                        TenantUserInvite.consumed_at.is_(None),
                    )
                )
                stale_ti = list(_ti_res.scalars().all())
                for ti in stale_ti:
                    ti.consumed_at = now
                await tdb.flush()
                imap = await db.scalar(
                    select(PlatformTenantUserMap).where(
                        PlatformTenantUserMap.tenant_id == int(tenant_id),
                        PlatformTenantUserMap.platform_user_id == str(inviter_user_id),
                    )
                )
                inviter_tid = imap.tenant_user_id if imap else None
                tinv = TenantUserInvite(
                    tenant_id=int(tenant_id),
                    token_hash=token_hash,
                    tenant_user_id=int(pmap_u.tenant_user_id),
                    inviter_tenant_user_id=inviter_tid,
                    expires_at=expires_at,
                )
                tdb.add(tinv)
                await tdb.commit()
                break

    invite = UserInvite(
        token_hash=token_hash,
        user_id=user.id,
        tenant_id=tenant_id,
        inviter_user_id=inviter_user_id,
        expires_at=expires_at,
    )
    db.add(invite)

    base = settings.base_domain or request.url.hostname or "truckerp.me"
    scheme = request.url.scheme or "https"
    invite_link = f"{scheme}://{tenant.slug}.{base}/accept-invite?token={raw_token}"

    email_sent = True
    try:
        await send_user_invite_email(
            to=user.email,
            workspace_name=tenant.name,
            workspace_slug=tenant.slug,
            invite_link=invite_link,
            expires_hours=INVITE_EXPIRY_HOURS,
        )
    except Exception as e:
        logger.warning("invite resend: send_email failed: %s", e)
        email_sent = False
        if not getattr(settings, "secure_cookies", True):
            logger.warning("invite resend: DEV invite_link email=%s link=%s", user.email, invite_link)

    await db.commit()
    return {
        "ok": True,
        "email": user.email,
        "status": "invited",
        "message": (
            "Invite email sent again."
            if email_sent
            else "Invite renewed but email failed to send. Configure SMTP (Admin → Integrations) or copy the link from server logs."
        ),
        "email_sent": email_sent,
    }


class UserMemberOut(BaseModel):
    """Approved temporary shape: username, email, phone, access_level (READ_ONLY|FULL_ACCESS)."""
    user_id: str
    username: str
    email: str
    phone: str | None
    access_level: str  # READ_ONLY | FULL_ACCESS
    membership_status: str
    joined_at: str


class SignInSecurityOut(BaseModel):
    """Sign-in protection detail for tenant admin user drawer (this API instance)."""

    sign_in_status: str
    all_clear: bool
    reasons: list[str]
    trigger_sources: list[str]
    timestamps: dict[str, str | None]
    restriction_summary: dict[str, Any]
    lock_scope: dict[str, Any]
    note: str


class InviteUserRequest(BaseModel):
    """Approved temporary fields: username, email, phone, access_level."""
    username: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    access_level: str = Field(default="READ_ONLY", description="READ_ONLY or FULL_ACCESS")


@router.get("/users", response_model=list[UserMemberOut])
async def list_tenant_users(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users in this tenant. Requires tenant membership. READ_ONLY and FULL_ACCESS can list."""

    members = (
        await db.scalars(
            select(PlatformTenantMember)
            .where(PlatformTenantMember.tenant_id == tenant_id)
            .options(selectinload(PlatformTenantMember.platform_user))
        )
    ).all()
    result = []
    for m in members:
        membership = await db.scalar(
            select(TenantMembership).where(
                TenantMembership.user_id == m.platform_user_id,
                TenantMembership.tenant_id == tenant_id,
            ).limit(1)
        )
        display = (
            (m.platform_user.username or "").strip()
            or f"{(m.platform_user.first_name or '')} {(m.platform_user.last_name or '')}".strip()
            or m.platform_user.email
        )
        result.append(
            UserMemberOut(
                user_id=m.platform_user_id,
                username=display,
                email=m.platform_user.email,
                phone=getattr(m.platform_user, "phone", None) or None,
                access_level=role_to_access_level(m.role or "TENANT_MEMBER"),
                membership_status=membership.status if membership else "unknown",
                joined_at=membership.joined_at.isoformat() if membership and membership.joined_at else "",
            )
        )
    return result


@router.get("/users/{user_id}/sign-in-security", response_model=SignInSecurityOut)
async def get_user_sign_in_security(
    user_id: str,
    tenant_id: int = Depends(require_tenant),
    _: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Workspace member sign-in protection (detail drawer). READ_ONLY and FULL_ACCESS."""
    ptm = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.tenant_id == tenant_id,
            PlatformTenantMember.platform_user_id == user_id,
        ).limit(1)
    )
    if not ptm:
        raise HTTPException(status_code=404, detail="User not found in this workspace")

    pu = await db.get(PlatformUser, user_id)
    if not pu or not (pu.email or "").strip():
        raise HTTPException(status_code=400, detail="User has no email")

    email_norm = normalize_auth_email(pu.email)
    if not email_norm:
        raise HTTPException(status_code=400, detail="Invalid email for user")

    panel = await build_sign_in_security_panel(tenant_id, email_norm)
    return SignInSecurityOut.model_validate(panel)


@router.post("/users/{user_id}/unlock-sign-in")
async def unlock_user_sign_in_for_tenant(
    user_id: str,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Clear password-fail streak + tenant+email login/step-up buckets for a member's email.
    FULL_ACCESS only. Does not change password or clear IP-wide login throttle.
    """
    if not has_full_access(current_user.role):
        raise HTTPException(
            status_code=403,
            detail="Full access required to unlock sign-in.",
        )

    ptm = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.tenant_id == tenant_id,
            PlatformTenantMember.platform_user_id == user_id,
        ).limit(1)
    )
    if not ptm:
        raise HTTPException(status_code=404, detail="User not found in this workspace")

    pu = await db.get(PlatformUser, user_id)
    if not pu or not (pu.email or "").strip():
        raise HTTPException(status_code=400, detail="User has no email")

    email_norm = normalize_auth_email(pu.email)
    if not email_norm:
        raise HTTPException(status_code=400, detail="Invalid email for user")

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

    logger.info(
        "tenant_admin.unlock_sign_in tenant_id=%s actor=%s target=%s email_norm=%s streak_deleted=%s "
        "mandated_next_sign_in_verification=%s",
        tenant_id,
        current_user.user.id,
        user_id,
        email_norm,
        streak_deleted,
        mandated_next_sign_in_verification,
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
        "ok": True,
        "mandated_next_sign_in_verification": mandated_next_sign_in_verification,
        "cleared": {
            "platform_login_password_fail_streaks": {"rows_deleted": streak_deleted},
            "rate_limiters": rate_cleared,
        },
        "state_after": state_after,
        "note": "IP-wide login throttle is not cleared. If sign-in still fails, wait or use another network.",
        "operator_message": operator_message,
    }


@router.post("/users/invite")
async def invite_user(
    payload: InviteUserRequest,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user to this tenant by email. Sends set-password email. FULL_ACCESS required; READ_ONLY gets 403."""
    if not has_full_access(current_user.role):
        raise HTTPException(
            status_code=403,
            detail="Full access required to invite users. Your role has read-only access.",
        )

    email_norm = normalize_auth_email(payload.email)
    role = access_level_to_role(payload.access_level)

    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
    existing_ptm = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.tenant_id == tenant_id,
            PlatformTenantMember.platform_user_id == user.id,
        ).limit(1)
    ) if user else None

    if existing_ptm:
        tm_row = await db.scalar(
            select(TenantMembership).where(
                TenantMembership.user_id == user.id,
                TenantMembership.tenant_id == tenant_id,
            ).limit(1)
        )
        mstatus = (tm_row.status if tm_row else "").strip().lower()
        if mstatus == "active":
            raise HTTPException(status_code=400, detail="User is already a member of this workspace")
        if mstatus == "invited":
            # Pending invite: allow resend (invalidate old tokens, new email).
            if existing_ptm.role != role:
                existing_ptm.role = role
                await db.flush()
            return await _perform_invite_resend(
                db,
                tenant_id=tenant_id,
                tenant=tenant,
                user=user,
                inviter_user_id=current_user.user.id,
                request=request,
            )

        raise HTTPException(
            status_code=400,
            detail=f"User already has access in this workspace (status: {tm_row.status or 'unknown'}).",
        )

    if not user:
        username_val = (payload.username or "").strip() or email_norm
        # Case-insensitive uniqueness: check before insert
        existing_username = await db.scalar(
            select(PlatformUser.id).where(
                func.lower(PlatformUser.username) == username_val.lower(),
                PlatformUser.username.isnot(None),
            ).limit(1)
        )
        if existing_username:
            raise HTTPException(status_code=400, detail="Username already taken")
        user = PlatformUser(
            email=email_norm,
            username=username_val,
            first_name=None,
            last_name=None,
            phone=(payload.phone or "").strip() or None,
            password_hash=None,
            status="ACTIVE",
        )
        db.add(user)
        await db.flush()

    ptm = PlatformTenantMember(
        tenant_id=tenant_id,
        platform_user_id=user.id,
        role=role,
    )
    db.add(ptm)
    await db.flush()

    tm = TenantMembership(
        user_id=user.id,
        tenant_id=tenant_id,
        status="invited",
        is_break_glass_owner=False,
    )
    db.add(tm)
    await db.flush()

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRY_HOURS)

    if tenant_uses_tenant_db_auth(getattr(tenant, "tenant_auth_mode", None)):
        imap = await db.scalar(
            select(PlatformTenantUserMap).where(
                PlatformTenantUserMap.tenant_id == int(tenant_id),
                PlatformTenantUserMap.platform_user_id == str(current_user.user.id),
            )
        )
        inviter_tid = imap.tenant_user_id if imap else None
        tenant_uid: int | None = None
        async for tdb in open_tenant_session_by_id(int(tenant_id)):
            tu = TenantUser(
                tenant_id=int(tenant_id),
                email_norm=email_norm,
                first_name=user.first_name,
                last_name=user.last_name,
                password_hash=None,
                status="ACTIVE",
            )
            tdb.add(tu)
            await tdb.flush()
            twm = TenantWorkspaceMember(
                tenant_id=int(tenant_id),
                tenant_user_id=tu.id,
                status="invited",
                role=role,
            )
            tdb.add(twm)
            tinv = TenantUserInvite(
                tenant_id=int(tenant_id),
                token_hash=token_hash,
                tenant_user_id=tu.id,
                inviter_tenant_user_id=inviter_tid,
                expires_at=expires_at,
            )
            tdb.add(tinv)
            await tdb.commit()
            tenant_uid = int(tu.id)
            break
        db.add(
            PlatformTenantUserMap(
                platform_user_id=str(user.id),
                tenant_id=int(tenant_id),
                tenant_user_id=int(tenant_uid),
            )
        )
        await db.flush()

    invite = UserInvite(
        token_hash=token_hash,
        user_id=user.id,
        tenant_id=tenant_id,
        inviter_user_id=current_user.user.id,
        expires_at=expires_at,
    )
    db.add(invite)

    base = settings.base_domain or request.url.hostname or "truckerp.me"
    scheme = request.url.scheme or "https"
    invite_link = f"{scheme}://{tenant.slug}.{base}/accept-invite?token={raw_token}"

    email_sent = True
    try:
        await send_user_invite_email(
            to=user.email,
            workspace_name=tenant.name,
            workspace_slug=tenant.slug,
            invite_link=invite_link,
            expires_hours=INVITE_EXPIRY_HOURS,
        )
    except Exception as e:
        logger.warning("invite_user: send_email failed: %s", e)
        email_sent = False
        if not getattr(settings, "secure_cookies", True):
            logger.warning("invite_user: DEV invite_link email=%s link=%s", user.email, invite_link)

    await db.commit()
    return {
        "ok": True,
        "email": user.email,
        "status": "invited",
        "message": (
            "Invite sent"
            if email_sent
            else "Invite created but email failed to send. Configure SMTP or check server logs."
        ),
        "email_sent": email_sent,
    }


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Suspend a user's access to this tenant. Changes TenantMembership.status only; does NOT touch PlatformUser.status. FULL_ACCESS required."""
    if not has_full_access(current_user.role):
        raise HTTPException(
            status_code=403,
            detail="Full access required to suspend users. Your role has read-only access.",
        )
    if user_id == current_user.user.id:
        raise HTTPException(status_code=400, detail="Cannot suspend yourself")

    tm = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        ).limit(1)
    )
    if not tm:
        raise HTTPException(status_code=404, detail="User not found in this workspace")
    tm.status = "suspended"
    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))
    if tenant and tenant_uses_tenant_db_auth(getattr(tenant, "tenant_auth_mode", None)):
        pmap = await db.scalar(
            select(PlatformTenantUserMap).where(
                PlatformTenantUserMap.tenant_id == int(tenant_id),
                PlatformTenantUserMap.platform_user_id == str(user_id),
            )
        )
        if pmap:
            async for tdb in open_tenant_session_by_id(int(tenant_id)):
                twm = await tdb.scalar(
                    select(TenantWorkspaceMember).where(
                        TenantWorkspaceMember.tenant_id == int(tenant_id),
                        TenantWorkspaceMember.tenant_user_id == int(pmap.tenant_user_id),
                    )
                )
                if twm:
                    twm.status = "suspended"
                await tdb.commit()
                break
    await db.commit()
    return {"ok": True, "status": "suspended"}


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate a suspended user's access. Changes TenantMembership.status only; does NOT touch PlatformUser.status. FULL_ACCESS required."""
    if not has_full_access(current_user.role):
        raise HTTPException(
            status_code=403,
            detail="Full access required to reactivate users. Your role has read-only access.",
        )

    tm = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        ).limit(1)
    )
    if not tm:
        raise HTTPException(status_code=404, detail="User not found in this workspace")
    tm.status = "active"
    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))
    if tenant and tenant_uses_tenant_db_auth(getattr(tenant, "tenant_auth_mode", None)):
        pmap = await db.scalar(
            select(PlatformTenantUserMap).where(
                PlatformTenantUserMap.tenant_id == int(tenant_id),
                PlatformTenantUserMap.platform_user_id == str(user_id),
            )
        )
        if pmap:
            async for tdb in open_tenant_session_by_id(int(tenant_id)):
                twm = await tdb.scalar(
                    select(TenantWorkspaceMember).where(
                        TenantWorkspaceMember.tenant_id == int(tenant_id),
                        TenantWorkspaceMember.tenant_user_id == int(pmap.tenant_user_id),
                    )
                )
                if twm:
                    twm.status = "active"
                await tdb.commit()
                break
    await db.commit()
    return {"ok": True, "status": "active"}


@router.post("/users/{user_id}/resend-invite")
async def resend_invite_for_user(
    user_id: str,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resend invite email for a user stuck in *invited* status. FULL_ACCESS required."""
    if not has_full_access(current_user.role):
        raise HTTPException(
            status_code=403,
            detail="Full access required to resend invites.",
        )
    if user_id == current_user.user.id:
        raise HTTPException(status_code=400, detail="Cannot resend invite to yourself")

    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user = await db.get(PlatformUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ptm = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.tenant_id == tenant_id,
            PlatformTenantMember.platform_user_id == user_id,
        ).limit(1)
    )
    if not ptm:
        raise HTTPException(status_code=404, detail="User is not in this workspace")

    tm = await db.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        ).limit(1)
    )
    if not tm or (tm.status or "").strip().lower() != "invited":
        raise HTTPException(
            status_code=400,
            detail="Resend is only for users who have not finished accepting their invite yet.",
        )

    return await _perform_invite_resend(
        db,
        tenant_id=tenant_id,
        tenant=tenant,
        user=user,
        inviter_user_id=current_user.user.id,
        request=request,
    )


@router.delete("/users/{user_id}")
async def remove_user_from_workspace(
    user_id: str,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a user from this workspace (membership + pending invites).
    If they have no other workspace memberships, delete the platform user so they can be invited fresh.
    FULL_ACCESS required. Cannot remove yourself.
    """
    if not has_full_access(current_user.role):
        raise HTTPException(
            status_code=403,
            detail="Full access required to remove users.",
        )
    if user_id == current_user.user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from the workspace")

    ptm = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.tenant_id == tenant_id,
            PlatformTenantMember.platform_user_id == user_id,
        ).limit(1)
    )
    if not ptm:
        raise HTTPException(status_code=404, detail="User not found in this workspace")

    await db.execute(
        delete(UserInvite).where(
            UserInvite.user_id == user_id,
            UserInvite.tenant_id == tenant_id,
        )
    )
    await db.execute(
        delete(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    await db.execute(
        delete(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user_id,
            PlatformTenantMember.tenant_id == tenant_id,
        )
    )
    await db.flush()

    other_memberships = await db.scalar(
        select(func.count()).select_from(PlatformTenantMember).where(PlatformTenantMember.platform_user_id == user_id)
    )
    if other_memberships == 0:
        orphan = await db.get(PlatformUser, user_id)
        if orphan:
            await db.delete(orphan)

    await db.commit()
    return {"ok": True, "message": "User removed from this workspace"}


# Tenant-admin password reset removed: password management remains platform-side.
# Use /api/v1/auth/forgot-password (user-initiated) for now.
