"""
Challenge-bound login step-up OTP: platform_login_otp_challenges + platform_otp_tokens (LOGIN_STEP_UP + tenant_id + login_challenge_id).
Reuses app.utils.otp and send_otp_email_for_purpose; never touches signup verify/provision.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.platform import (
    OTPPurpose,
    PlatformLoginOtpChallenge,
    PlatformOTPToken,
    PlatformUser,
)
from app.models.tenant_auth import TenantUser, TenantWorkspaceMember
from app.deps.tenant_db import open_tenant_session_by_id
from app.services.login_failure_audit import email_fingerprint
from app.services.login_password_abuse import login_password_challenge_armed
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
from app.utils.auth_identity import normalize_auth_email
from app.utils.email import send_otp_email_for_purpose
from app.utils.otp import check_otp, generate_otp, get_otp_expiration, hash_otp

logger = logging.getLogger(__name__)

LOGIN_STEP_UP_PURPOSE = OTPPurpose.LOGIN_STEP_UP.value
CHALLENGE_TTL_MINUTES = 15

STEP_UP_403_BODY_DETAIL = "Additional verification required."


async def login_step_up_otp_required_for_this_attempt(tenant_id: int, email_norm: str) -> bool:
    """
    Per-attempt step-up: true when password-fail streak is armed for this tenant+email, or test hook login_step_up_otp_required.
    """
    if getattr(settings, "login_step_up_otp_required", False):
        return True
    return await login_password_challenge_armed(tenant_id, email_norm)


async def get_or_create_open_login_otp_challenge_after_password(
    db: AsyncSession, tenant_id: int, email_norm: str
) -> str:
    now = datetime.now(timezone.utc)
    existing = await db.scalar(
        select(PlatformLoginOtpChallenge)
        .where(
            PlatformLoginOtpChallenge.tenant_id == int(tenant_id),
            PlatformLoginOtpChallenge.email_norm == email_norm,
            PlatformLoginOtpChallenge.otp_verified_at.is_(None),
            PlatformLoginOtpChallenge.session_issued_at.is_(None),
        )
        .order_by(PlatformLoginOtpChallenge.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        exp = existing.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now <= exp:
            return existing.id
    return await create_login_otp_challenge_after_password(db, tenant_id, email_norm)


async def create_login_otp_challenge_after_password(db: AsyncSession, tenant_id: int, email_norm: str) -> str:
    now = datetime.now(timezone.utc)
    cid = str(uuid.uuid4())
    row = PlatformLoginOtpChallenge(
        id=cid,
        tenant_id=int(tenant_id),
        email_norm=email_norm,
        created_at=now,
        expires_at=now + timedelta(minutes=CHALLENGE_TTL_MINUTES),
        password_verified_at=now,
    )
    db.add(row)
    await db.commit()
    logger.info(
        "event=otp_login_step_up_challenge_created tenant_id=%s email_fingerprint=%s challenge_id=%s",
        int(tenant_id),
        email_fingerprint(email_norm),
        cid,
    )
    return cid


def json_response_login_step_up_required(login_challenge_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": STEP_UP_403_BODY_DETAIL, "login_challenge_id": login_challenge_id},
    )


async def validate_challenge_ready_for_session(
    db: AsyncSession, challenge_id: str, tenant_id: int, email_norm: str
) -> bool:
    now = datetime.now(timezone.utc)
    row = await db.scalar(select(PlatformLoginOtpChallenge).where(PlatformLoginOtpChallenge.id == challenge_id))
    if row is None:
        return False
    if int(row.tenant_id) != int(tenant_id):
        return False
    if (row.email_norm or "") != email_norm:
        return False
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        return False
    if row.otp_verified_at is None:
        return False
    if row.session_issued_at is not None:
        return False
    return True


async def mark_challenge_session_issued(db: AsyncSession, challenge_id: str) -> bool:
    """Single-use: returns True if this call transitioned session_issued from null to set."""
    now = datetime.now(timezone.utc)
    res = await db.execute(
        update(PlatformLoginOtpChallenge)
        .where(
            PlatformLoginOtpChallenge.id == challenge_id,
            PlatformLoginOtpChallenge.session_issued_at.is_(None),
        )
        .values(session_issued_at=now)
        .returning(PlatformLoginOtpChallenge.id)
    )
    rid = res.scalar_one_or_none()
    await db.commit()
    return rid is not None


async def login_step_up_challenge_gate_after_password(
    db: AsyncSession,
    *,
    tenant_id: int,
    email_norm: str,
    login_challenge_id: str | None,
) -> JSONResponse | None:
    """
    After password verified: either consume challenge + proceed (None), create challenge + 403, or proceed without step-up.
    Raises HTTPException 401 for invalid finalize.
    """
    from fastapi import HTTPException, status

    lc = (login_challenge_id or "").strip()
    if lc:
        if not await validate_challenge_ready_for_session(db, lc, tenant_id, email_norm):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not await mark_challenge_session_issued(db, lc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        logger.info(
            "event=otp_login_step_up_challenge_consumed tenant_id=%s email_fingerprint=%s challenge_id=%s",
            int(tenant_id),
            email_fingerprint(email_norm),
            lc,
        )
        return None
    if await login_step_up_otp_required_for_this_attempt(tenant_id, email_norm):
        cid = await get_or_create_open_login_otp_challenge_after_password(db, tenant_id, email_norm)
        return json_response_login_step_up_required(cid)
    return None


async def _load_challenge_for_issue_verify(
    db: AsyncSession, tenant_id: int, challenge_id: str
) -> PlatformLoginOtpChallenge | None:
    row = await db.scalar(
        select(PlatformLoginOtpChallenge).where(
            PlatformLoginOtpChallenge.id == challenge_id,
            PlatformLoginOtpChallenge.tenant_id == int(tenant_id),
        )
    )
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        return None
    if row.session_issued_at is not None:
        return None
    return row


async def issue_login_step_up_otp_for_challenge(
    *,
    db: AsyncSession,
    request,
    tenant_id: int,
    login_challenge_id: str,
) -> None:
    """
    Send OTP for an existing challenge (password already verified on this attempt). Uniform caller response for enumeration safety.
    """
    ch = await _load_challenge_for_issue_verify(db, tenant_id, login_challenge_id.strip())
    fp = email_fingerprint(ch.email_norm if ch else "")
    logger.info(
        "event=otp_login_step_up_issue purpose=%s tenant_id=%s challenge_id=%s eligible=%s path=%s",
        LOGIN_STEP_UP_PURPOSE,
        int(tenant_id),
        login_challenge_id,
        ch is not None,
        getattr(request, "url", None) and request.url.path,
    )
    if ch is None:
        return
    if ch.otp_verified_at is not None:
        return
    email_norm = ch.email_norm
    user = await db.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
    uid = str(user.id) if user else None
    now = datetime.now(timezone.utc)
    await db.execute(
        update(PlatformOTPToken)
        .where(
            PlatformOTPToken.purpose == LOGIN_STEP_UP_PURPOSE,
            PlatformOTPToken.login_challenge_id == ch.id,
            PlatformOTPToken.consumed_at.is_(None),
            PlatformOTPToken.superseded_at.is_(None),
        )
        .values(superseded_at=now)
    )
    otp = generate_otp()
    row = PlatformOTPToken(
        purpose=LOGIN_STEP_UP_PURPOSE,
        email=email_norm,
        tenant_id=int(tenant_id),
        login_challenge_id=ch.id,
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


async def verify_login_step_up_otp_for_challenge(
    *,
    db: AsyncSession,
    request,
    tenant_id: int,
    login_challenge_id: str,
    otp_code: str,
) -> bool:
    ch = await _load_challenge_for_issue_verify(db, tenant_id, login_challenge_id.strip())
    fp = email_fingerprint(ch.email_norm if ch else "")
    logger.info(
        "event=otp_login_step_up_verify_attempt purpose=%s tenant_id=%s challenge_id=%s path=%s",
        LOGIN_STEP_UP_PURPOSE,
        int(tenant_id),
        login_challenge_id,
        getattr(request, "url", None) and request.url.path,
    )
    if ch is None:
        return False
    if ch.otp_verified_at is not None:
        return False
    otp_row = await db.scalar(
        select(PlatformOTPToken)
        .where(
            PlatformOTPToken.purpose == LOGIN_STEP_UP_PURPOSE,
            PlatformOTPToken.tenant_id == int(tenant_id),
            PlatformOTPToken.login_challenge_id == ch.id,
            PlatformOTPToken.consumed_at.is_(None),
            PlatformOTPToken.superseded_at.is_(None),
        )
        .order_by(PlatformOTPToken.created_at.desc())
        .limit(1)
    )
    if otp_row is None:
        return False
    ok, _ = check_otp(otp_code.strip(), otp_row)
    if not ok:
        return False
    now = datetime.now(timezone.utc)
    otp_row.consumed_at = now
    ch.otp_verified_at = now
    await db.commit()
    logger.info(
        "event=otp_login_step_up_verify_ok purpose=%s tenant_id=%s challenge_id=%s email_fingerprint=%s",
        LOGIN_STEP_UP_PURPOSE,
        int(tenant_id),
        ch.id,
        fp,
    )
    return True
