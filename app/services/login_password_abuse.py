"""
Shared login abuse state in the platform DB: password-verification failure streaks per tenant + email fingerprint.

Rate limiting stays in app.utils.rate_limit (in-memory). This module only tracks failures after verify_password runs and fails.

Persists via AsyncSessionLocal + commit (same pattern as login_failure_audit); get_db does not auto-commit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.platform import PlatformLoginPasswordFailStreak
from app.services.login_failure_audit import email_fingerprint
from app.services.turnstile import verify_turnstile_token

logger = logging.getLogger(__name__)

# Rolling window for streak (same row in platform_login_password_fail_streaks).
LOGIN_PASSWORD_FAIL_WINDOW_SECONDS = 3600

# After this many failed password verifications, Turnstile is required before password check (when configured).
LOGIN_PASSWORD_TURNSTILE_THRESHOLD = 3

# After this many failed password verifications, a correct password still requires email OTP step-up before session.
LOGIN_PASSWORD_OTP_STEP_UP_THRESHOLD = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _load_streak_row(db: AsyncSession, tenant_id: int, email_norm: str) -> PlatformLoginPasswordFailStreak | None:
    fp = email_fingerprint(email_norm)
    return await db.scalar(
        select(PlatformLoginPasswordFailStreak).where(
            PlatformLoginPasswordFailStreak.tenant_id == int(tenant_id),
            PlatformLoginPasswordFailStreak.email_fingerprint == fp,
        )
    )


def _window_expired(window_started_at: datetime, now: datetime) -> bool:
    delta = (now - window_started_at).total_seconds()
    return delta > float(LOGIN_PASSWORD_FAIL_WINDOW_SECONDS)


async def _login_password_fail_streak_count(tenant_id: int, email_norm: str) -> int:
    """Failed password attempts in the current non-expired window, or 0."""
    now = _utcnow()
    async with AsyncSessionLocal() as adb:
        row = await _load_streak_row(adb, tenant_id, email_norm)
        if row is None:
            return 0
        if _window_expired(row.window_started_at, now):
            return 0
        return int(row.streak_count or 0)


async def login_password_turnstile_armed(tenant_id: int, email_norm: str) -> bool:
    """True when Turnstile should run before password check for this tenant + email."""
    return await _login_password_fail_streak_count(tenant_id, email_norm) >= LOGIN_PASSWORD_TURNSTILE_THRESHOLD


async def login_password_otp_step_up_armed(tenant_id: int, email_norm: str) -> bool:
    """True when a correct password must still go through OTP step-up for this tenant + email."""
    return await _login_password_fail_streak_count(tenant_id, email_norm) >= LOGIN_PASSWORD_OTP_STEP_UP_THRESHOLD


async def assert_login_human_verification_if_armed(
    tenant_id: int,
    email_norm: str,
    turnstile_token: str | None,
) -> None:
    """
    If Turnstile is configured and the streak is armed, require a passing siteverify before password check.
    Raises HTTP 403 with a static message (does not reveal password or email validity).
    """
    if not (settings.turnstile_secret_key or "").strip():
        return
    if not await login_password_turnstile_armed(tenant_id, email_norm):
        return

    site_cfg = (getattr(settings, "turnstile_site_key", None) or "").strip()
    token = (turnstile_token or "").strip()

    if not token:
        logger.info(
            "event=login_turnstile_challenge_403 tenant_id=%s email_fingerprint=%s "
            "reason=missing_turnstile_token api_turnstile_site_key_configured=%s",
            int(tenant_id),
            email_fingerprint(email_norm),
            bool(site_cfg),
        )
        if not site_cfg:
            logger.error(
                "event=turnstile_configuration_error tenant_id=%s email_fingerprint=%s "
                "CONFIGURATION: TURNSTILE_SECRET_KEY is set (login will require Turnstile after failed attempts), "
                "but TURNSTILE_SITE_KEY is empty on the API. The login page loads the site key from "
                "GET /api/v1/public/tenant/{slug}; without the site key, browsers cannot show the widget. "
                "Set TURNSTILE_SITE_KEY to the Cloudflare Turnstile site key (public) matching secrets.",
                int(tenant_id),
                email_fingerprint(email_norm),
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Additional verification required.",
        )

    ok = await verify_turnstile_token(turnstile_token)
    if ok:
        return

    logger.warning(
        "event=login_turnstile_challenge_403 tenant_id=%s email_fingerprint=%s "
        "reason=turnstile_siteverify_failed (invalid, expired, or mismatched secret)",
        int(tenant_id),
        email_fingerprint(email_norm),
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Additional verification required.",
    )


async def record_login_password_verify_failure(tenant_id: int, email_norm: str) -> None:
    """Call only after verify_password ran and failed for this workspace + identity."""
    now = _utcnow()
    fp = email_fingerprint(email_norm)
    async with AsyncSessionLocal() as adb:
        row = await _load_streak_row(adb, tenant_id, email_norm)
        if row is None or _window_expired(row.window_started_at, now):
            if row is not None:
                await adb.delete(row)
                await adb.flush()
            adb.add(
                PlatformLoginPasswordFailStreak(
                    tenant_id=int(tenant_id),
                    email_fingerprint=fp,
                    streak_count=1,
                    window_started_at=now,
                    updated_at=now,
                )
            )
        else:
            row.streak_count = int(row.streak_count or 0) + 1
            row.updated_at = now
        await adb.commit()


async def get_login_password_fail_streak_snapshot(tenant_id: int, email_norm: str) -> dict[str, Any]:
    """Read-only streak for platform unlock UI (no row / expired window => clear)."""
    now = _utcnow()
    async with AsyncSessionLocal() as adb:
        row = await _load_streak_row(adb, tenant_id, email_norm)
        if row is None or _window_expired(row.window_started_at, now):
            return {
                "has_active_window": False,
                "streak_count": 0,
                "turnstile_armed": False,
                "otp_step_up_armed": False,
                "window_started_at": None,
                "window_expires_at": None,
                "streak_last_activity_at": None,
            }
        count = int(row.streak_count or 0)
        ws = row.window_started_at
        if ws.tzinfo is None:
            ws = ws.replace(tzinfo=timezone.utc)
        exp = ws + timedelta(seconds=float(LOGIN_PASSWORD_FAIL_WINDOW_SECONDS))
        lu = row.updated_at
        if lu is not None and lu.tzinfo is None:
            lu = lu.replace(tzinfo=timezone.utc)
        return {
            "has_active_window": True,
            "streak_count": count,
            "turnstile_armed": count >= LOGIN_PASSWORD_TURNSTILE_THRESHOLD,
            "otp_step_up_armed": count >= LOGIN_PASSWORD_OTP_STEP_UP_THRESHOLD,
            "window_started_at": ws.isoformat(),
            "window_expires_at": exp.isoformat(),
            "streak_last_activity_at": lu.isoformat() if lu else None,
        }


async def clear_login_password_fail_streak(tenant_id: int, email_norm: str) -> int:
    """Delete streak row(s) for tenant + email. Returns deleted row count (0 or 1)."""
    fp = email_fingerprint(email_norm)
    async with AsyncSessionLocal() as adb:
        result = await adb.execute(
            delete(PlatformLoginPasswordFailStreak).where(
                PlatformLoginPasswordFailStreak.tenant_id == int(tenant_id),
                PlatformLoginPasswordFailStreak.email_fingerprint == fp,
            )
        )
        await adb.commit()
        return int(result.rowcount or 0)
