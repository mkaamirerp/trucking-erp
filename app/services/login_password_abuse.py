"""
Shared login abuse state in the platform DB: password-verification failure streaks per tenant + email fingerprint.

Rate limiting stays in app.utils.rate_limit (in-memory). This module only tracks failures after verify_password runs and fails.

Persists via AsyncSessionLocal + commit (same pattern as login_failure_audit); get_db does not auto-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.platform import PlatformLoginPasswordFailStreak
from app.services.login_failure_audit import email_fingerprint
from app.services.turnstile import verify_turnstile_token

# After this many failed password checks within the window, the next login attempt must pass Turnstile first.
LOGIN_PASSWORD_FAIL_CHALLENGE_THRESHOLD = 3
LOGIN_PASSWORD_FAIL_WINDOW_SECONDS = 3600


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


async def login_password_challenge_armed(tenant_id: int, email_norm: str) -> bool:
    """True when this tenant + email has >= threshold failures in the current non-expired window."""
    now = _utcnow()
    async with AsyncSessionLocal() as adb:
        row = await _load_streak_row(adb, tenant_id, email_norm)
        if row is None:
            return False
        if _window_expired(row.window_started_at, now):
            return False
        return int(row.streak_count or 0) >= LOGIN_PASSWORD_FAIL_CHALLENGE_THRESHOLD


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
    if not await login_password_challenge_armed(tenant_id, email_norm):
        return
    ok = await verify_turnstile_token(turnstile_token)
    if ok:
        return
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


async def clear_login_password_fail_streak(tenant_id: int, email_norm: str) -> None:
    fp = email_fingerprint(email_norm)
    async with AsyncSessionLocal() as adb:
        await adb.execute(
            delete(PlatformLoginPasswordFailStreak).where(
                PlatformLoginPasswordFailStreak.tenant_id == int(tenant_id),
                PlatformLoginPasswordFailStreak.email_fingerprint == fp,
            )
        )
        await adb.commit()
