"""
Login step-up OTP: platform_otp_tokens with OTPPurpose.LOGIN_STEP_UP + tenant_id.
Reuses app.utils.otp and send_otp_email_for_purpose; never touches signup verify/provision.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import OTPPurpose, PlatformOTPToken, PlatformTenant, PlatformTenantMember, PlatformUser
from app.models.tenant_auth import TenantUser, TenantWorkspaceMember
from app.deps.tenant_db import open_tenant_session_by_id
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
from app.services.login_failure_audit import email_fingerprint
from app.utils.auth_identity import normalize_auth_email
from app.utils.email import send_otp_email_for_purpose
from app.utils.jwt_auth import create_login_step_up_proof_token, decode_login_step_up_proof_token
from app.utils.otp import check_otp, generate_otp, get_otp_expiration, hash_otp

logger = logging.getLogger(__name__)

LOGIN_STEP_UP_PURPOSE = OTPPurpose.LOGIN_STEP_UP.value


async def email_has_membership_in_tenant(db: AsyncSession, tenant_id: int, email_norm: str) -> bool:
    """True if this normalized email has an active path to the workspace (platform or tenant-db auth)."""
    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))
    if not tenant:
        return False
    mode = getattr(tenant, "tenant_auth_mode", None) or "platform"
    if tenant_uses_tenant_db_auth(mode):
        async for tdb in open_tenant_session_by_id(int(tenant_id)):
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == int(tenant_id),
                    TenantUser.email_norm == email_norm,
                )
            )
            if not tu or (tu.status or "").upper() != "ACTIVE":
                return False
            twm = await tdb.scalar(
                select(TenantWorkspaceMember).where(
                    TenantWorkspaceMember.tenant_id == int(tenant_id),
                    TenantWorkspaceMember.tenant_user_id == tu.id,
                    TenantWorkspaceMember.status == "active",
                )
            )
            return twm is not None
        return False

    user = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
    if not user:
        return False
    m = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user.id,
            PlatformTenantMember.tenant_id == int(tenant_id),
        ).limit(1)
    )
    return m is not None


async def _supersede_open_login_tokens(db: AsyncSession, tenant_id: int, email_norm: str) -> None:
    now = datetime.now(timezone.utc)
    await db.execute(
        update(PlatformOTPToken)
        .where(
            PlatformOTPToken.purpose == LOGIN_STEP_UP_PURPOSE,
            PlatformOTPToken.tenant_id == int(tenant_id),
            PlatformOTPToken.email == email_norm,
            PlatformOTPToken.consumed_at.is_(None),
            PlatformOTPToken.superseded_at.is_(None),
        )
        .values(superseded_at=now)
    )


async def issue_login_step_up_otp(
    *,
    db: AsyncSession,
    request,
    tenant_id: int,
    email_raw: str,
) -> None:
    """
    If the email is a member of tenant_id, create OTP and send email. Always log with purpose.
    Caller returns generic HTTP 200 body (anti-enumeration).
    """
    email_norm = normalize_auth_email(email_raw)
    eligible = await email_has_membership_in_tenant(db, tenant_id, email_norm)
    fp = email_fingerprint(email_norm)
    logger.info(
        "event=otp_login_step_up_issue purpose=%s tenant_id=%s email_fingerprint=%s eligible=%s path=%s",
        LOGIN_STEP_UP_PURPOSE,
        int(tenant_id),
        fp,
        eligible,
        getattr(request, "url", None) and request.url.path,
    )
    if not eligible:
        return

    user = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
    uid = str(user.id) if user else None
    await _supersede_open_login_tokens(db, tenant_id, email_norm)
    otp = generate_otp()
    now = datetime.now(timezone.utc)
    row = PlatformOTPToken(
        purpose=LOGIN_STEP_UP_PURPOSE,
        email=email_norm,
        tenant_id=int(tenant_id),
        user_id=uid,
        onboarding_payload_id=None,
        otp_hash=hash_otp(otp),
        expires_at=get_otp_expiration(),
        request_ip=(request.client.host if request.client else None)[:45] if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:2000] or None,
        created_at=now,
    )
    db.add(row)
    await db.commit()
    try:
        await send_otp_email_for_purpose(email_norm, otp, purpose=LOGIN_STEP_UP_PURPOSE)
    except Exception as exc:
        logger.warning("otp_login_step_up_send_failed tenant_id=%s err=%s", tenant_id, exc)


async def verify_login_step_up_otp(
    *,
    db: AsyncSession,
    request,
    tenant_id: int,
    email_raw: str,
    otp_code: str,
) -> str | None:
    """
    Validates OTP row for purpose LOGIN_STEP_UP + tenant_id + email.
    Returns proof JWT on success, None if invalid (caller should use generic failure).
    """
    email_norm = normalize_auth_email(email_raw)
    fp = email_fingerprint(email_norm)
    logger.info(
        "event=otp_login_step_up_verify_attempt purpose=%s tenant_id=%s email_fingerprint=%s path=%s",
        LOGIN_STEP_UP_PURPOSE,
        int(tenant_id),
        fp,
        getattr(request, "url", None) and request.url.path,
    )
    otp_row = await db.scalar(
        select(PlatformOTPToken)
        .where(
            PlatformOTPToken.purpose == LOGIN_STEP_UP_PURPOSE,
            PlatformOTPToken.tenant_id == int(tenant_id),
            PlatformOTPToken.email == email_norm,
            PlatformOTPToken.consumed_at.is_(None),
            PlatformOTPToken.superseded_at.is_(None),
        )
        .order_by(PlatformOTPToken.created_at.desc())
        .limit(1)
    )
    if otp_row is None:
        return None
    ok, _reason = check_otp(otp_code, otp_row)
    if not ok:
        return None
    now = datetime.now(timezone.utc)
    otp_row.consumed_at = now
    await db.commit()
    proof = create_login_step_up_proof_token(
        tenant_id=int(tenant_id),
        email_norm=email_norm,
        otp_row_id=int(otp_row.id),
    )
    logger.info(
        "event=otp_login_step_up_verify_ok purpose=%s tenant_id=%s otp_row_id=%s email_fingerprint=%s",
        LOGIN_STEP_UP_PURPOSE,
        int(tenant_id),
        otp_row.id,
        fp,
    )
    return proof


async def validate_login_step_up_proof(
    db: AsyncSession,
    *,
    tenant_id: int,
    email_norm: str,
    proof_token: str | None,
) -> bool:
    """True if JWT matches tenant + email and consumed LOGIN_STEP_UP row."""
    payload = decode_login_step_up_proof_token(proof_token)
    if not payload:
        return False
    try:
        if int(payload.get("tenant_id") or 0) != int(tenant_id):
            return False
    except (TypeError, ValueError):
        return False
    if (payload.get("email_norm") or "") != email_norm:
        return False
    otp_id = payload.get("otp_id")
    if otp_id is None:
        return False
    try:
        oid = int(otp_id)
    except (TypeError, ValueError):
        return False
    row = await db.get(PlatformOTPToken, oid)
    if row is None:
        return False
    if row.purpose != LOGIN_STEP_UP_PURPOSE:
        return False
    if row.tenant_id is None or int(row.tenant_id) != int(tenant_id):
        return False
    if (row.email or "") != email_norm:
        return False
    if row.consumed_at is None:
        return False
    return True
