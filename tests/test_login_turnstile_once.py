"""Turnstile is consumed at most once per login attempt (apex + OTP completion)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.login_password_abuse import assert_login_human_verification_if_armed
from app.services.login_step_up_otp import challenge_carries_prior_human_verification


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace())


@pytest.mark.asyncio
async def test_apex_style_double_call_verifies_turnstile_exactly_once():
    """Apex tenant resolution then login() share one Request; siteverify must run once."""
    request = _request()
    verify = AsyncMock(return_value=True)
    with (
        patch.object(settings, "turnstile_secret_key", "unit-secret"),
        patch.object(settings, "turnstile_site_key", "unit-site"),
        patch(
            "app.services.login_password_abuse.login_password_turnstile_armed",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("app.services.login_password_abuse.verify_turnstile_token", verify),
    ):
        await assert_login_human_verification_if_armed(
            7, "owner@example.com", "once-token", request=request
        )
        await assert_login_human_verification_if_armed(
            7, "owner@example.com", "once-token", request=request
        )
    assert verify.await_count == 1


@pytest.mark.asyncio
async def test_successful_turnstile_then_password_path_does_not_reverify():
    request = _request()
    verify = AsyncMock(return_value=True)
    with (
        patch.object(settings, "turnstile_secret_key", "unit-secret"),
        patch(
            "app.services.login_password_abuse.login_password_turnstile_armed",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("app.services.login_password_abuse.verify_turnstile_token", verify),
    ):
        await assert_login_human_verification_if_armed(
            1, "a@example.com", "ok-token", request=request
        )
    assert verify.await_count == 1
    assert getattr(request.state, "login_turnstile_verified_fp")


@pytest.mark.asyncio
async def test_otp_completion_skips_consumed_turnstile_token():
    """OTP finalize must not require replaying a token already consumed on the password step."""
    verify = AsyncMock(return_value=True)
    with (
        patch.object(settings, "turnstile_secret_key", "unit-secret"),
        patch(
            "app.services.login_password_abuse.login_password_turnstile_armed",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("app.services.login_password_abuse.verify_turnstile_token", verify),
    ):
        await assert_login_human_verification_if_armed(
            1,
            "a@example.com",
            None,
            already_satisfied=True,
        )
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_turnstile_token_fails_when_armed():
    verify = AsyncMock(return_value=True)
    with (
        patch.object(settings, "turnstile_secret_key", "unit-secret"),
        patch.object(settings, "turnstile_site_key", "unit-site"),
        patch(
            "app.services.login_password_abuse.login_password_turnstile_armed",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("app.services.login_password_abuse.verify_turnstile_token", verify),
    ):
        with pytest.raises(HTTPException) as exc:
            await assert_login_human_verification_if_armed(1, "a@example.com", None)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Additional verification required."
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_turnstile_token_fails_when_armed():
    verify = AsyncMock(return_value=False)
    with (
        patch.object(settings, "turnstile_secret_key", "unit-secret"),
        patch(
            "app.services.login_password_abuse.login_password_turnstile_armed",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("app.services.login_password_abuse.verify_turnstile_token", verify),
    ):
        with pytest.raises(HTTPException) as exc:
            await assert_login_human_verification_if_armed(1, "a@example.com", "bad-token")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Additional verification required."
    assert verify.await_count == 1


@pytest.mark.asyncio
async def test_live_step_up_challenge_counts_as_prior_human_verification():
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        tenant_id=9,
        email_norm="a@example.com",
        expires_at=now + timedelta(minutes=10),
        session_issued_at=None,
        password_verified_at=now,
        otp_verified_at=now,
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=row)
    ok = await challenge_carries_prior_human_verification(
        db,
        tenant_id=9,
        email_norm="a@example.com",
        login_challenge_id="11111111-1111-1111-1111-111111111111",
    )
    assert ok is True


@pytest.mark.asyncio
async def test_foreign_or_spent_challenge_does_not_bypass_turnstile():
    now = datetime.now(timezone.utc)
    spent = SimpleNamespace(
        tenant_id=9,
        email_norm="a@example.com",
        expires_at=now + timedelta(minutes=10),
        session_issued_at=now,
        password_verified_at=now,
        otp_verified_at=now,
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=spent)
    assert (
        await challenge_carries_prior_human_verification(
            db,
            tenant_id=9,
            email_norm="a@example.com",
            login_challenge_id="11111111-1111-1111-1111-111111111111",
        )
        is False
    )

    other = SimpleNamespace(
        tenant_id=99,
        email_norm="a@example.com",
        expires_at=now + timedelta(minutes=10),
        session_issued_at=None,
        password_verified_at=now,
        otp_verified_at=now,
    )
    db.scalar = AsyncMock(return_value=other)
    assert (
        await challenge_carries_prior_human_verification(
            db,
            tenant_id=9,
            email_norm="a@example.com",
            login_challenge_id="11111111-1111-1111-1111-111111111111",
        )
        is False
    )

    db.scalar = AsyncMock(return_value=None)
    assert (
        await challenge_carries_prior_human_verification(
            db,
            tenant_id=9,
            email_norm="a@example.com",
            login_challenge_id="11111111-1111-1111-1111-111111111111",
        )
        is False
    )

    pending_otp = SimpleNamespace(
        tenant_id=9,
        email_norm="a@example.com",
        expires_at=now + timedelta(minutes=10),
        session_issued_at=None,
        password_verified_at=now,
        otp_verified_at=None,
    )
    db.scalar = AsyncMock(return_value=pending_otp)
    assert (
        await challenge_carries_prior_human_verification(
            db,
            tenant_id=9,
            email_norm="a@example.com",
            login_challenge_id="11111111-1111-1111-1111-111111111111",
        )
        is False
    )
