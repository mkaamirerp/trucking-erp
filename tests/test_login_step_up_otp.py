"""Challenge-bound login step-up OTP (platform_login_otp_challenges + platform_otp_tokens.login_challenge_id)."""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.platform import OTPPurpose, PlatformOTPToken, PlatformTenant
from app.services.login_unlock_step_up_pending import (
    login_step_up_pending_after_unlock_exists,
    set_login_step_up_pending_after_unlock,
)
from app.utils.auth_identity import normalize_auth_email
from app.utils.otp import generate_otp, hash_otp
from tests.test_tenant_auth_matrix import _fake_provision_tenant_db, _host

SKIP_NO_DB = not os.environ.get("DATABASE_URL")


async def _signup_workspace(ac: AsyncClient, slug: str, email: str, password: str, otp: str) -> str:
    with (
        patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock),
        patch("app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock),
        patch("app.routers.public_signup.send_otp_email", new_callable=AsyncMock),
        patch("app.routers.public_signup.generate_otp", return_value=otp),
    ):
        r = await ac.post(
            "/api/v1/public/signup",
            json={
                "workspace_slug": slug,
                "email": email,
                "password": password,
                "first_name": "L",
                "last_name": "SU",
                "phone": "+15551234567",
                "company_legal_name": "SU Inc",
                "address": {
                    "street": "1 St",
                    "city": "Toronto",
                    "region": "ON",
                    "postal": "M5V 1A1",
                    "country": "CA",
                },
            },
        )
    assert r.status_code == 201, r.text
    signup_id = r.json().get("signup_id")
    with patch("app.routers.public_signup.provision_tenant_db", AsyncMock(side_effect=_fake_provision_tenant_db)):
        vr = await ac.post(
            "/api/v1/public/verify-otp",
            json={"email": email, "otp": otp, "signup_id": signup_id},
        )
    assert vr.status_code == 200, vr.text
    return str(vr.json().get("slug"))


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_forced_login_step_up_full_flow():
    slug = f"lc_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, fixed_otp)

    origin = f"http://{_host(tenant_slug)}"
    with patch.object(settings, "login_step_up_otp_required", True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert lr.status_code == 403, lr.text
    body = lr.json()
    assert body.get("detail") == "Additional verification required."
    challenge_id = body.get("login_challenge_id")
    assert challenge_id and len(challenge_id) == 36

    otp_plain = generate_otp()
    with patch("app.services.login_step_up_otp.send_otp_email_for_purpose", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            ir = await ac.post("/api/v1/auth/login-step-up/issue", json={"login_challenge_id": challenge_id})
    assert ir.status_code == 200, ir.text

    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformOTPToken).where(
                PlatformOTPToken.login_challenge_id == challenge_id,
                PlatformOTPToken.purpose == OTPPurpose.LOGIN_STEP_UP.value,
                PlatformOTPToken.consumed_at.is_(None),
            )
        )
        assert row is not None
        row.otp_hash = hash_otp(otp_plain)
        await adb.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        vr = await ac.post(
            "/api/v1/auth/login-step-up/verify",
            json={"login_challenge_id": challenge_id, "otp": otp_plain},
        )
    assert vr.status_code == 200, vr.json() == {"ok": True}

    with patch.object(settings, "login_step_up_otp_required", True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            ok = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "login_challenge_id": challenge_id},
            )
    assert ok.status_code == 200, ok.text
    data = ok.json()
    assert data.get("ok") is True
    assert data.get("familiar_device") is False

    with patch.object(settings, "login_step_up_otp_required", True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            replay = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "login_challenge_id": challenge_id},
            )
    assert replay.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_armed_password_streak_triggers_403_without_force_flag():
    slug = f"lc2_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, fixed_otp)

    origin = f"http://{_host(tenant_slug)}"
    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            for _ in range(5):
                bad = await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
                assert bad.status_code == 401
    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert lr.status_code == 403
    assert lr.json().get("login_challenge_id")


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_three_failed_passwords_then_success_no_otp_under_otp_threshold():
    """Turnstile threshold is 3; OTP step-up threshold is 5 — three failures then correct password should not demand OTP."""
    slug = f"lc4_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, fixed_otp)

    origin = f"http://{_host(tenant_slug)}"
    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            for _ in range(3):
                bad = await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
                assert bad.status_code == 401
            ok = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert ok.status_code == 200, ok.text
    assert ok.json().get("login_challenge_id") is None
    assert ok.json().get("ok") is True


@pytest.mark.asyncio
async def test_login_step_up_issue_rejected_on_apex_host():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        r = await ac.post(
            "/api/v1/auth/login-step-up/issue",
            json={"login_challenge_id": str(uuid.uuid4())},
        )
    assert r.status_code == 403
    assert r.json().get("detail") == "Use your company sign-in URL to continue."


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_signup_otp_row_has_no_login_challenge_id():
    slug = f"lc3_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"
    norm = normalize_auth_email(email)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        await _signup_workspace(ac, slug, email, password, fixed_otp)

    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformOTPToken).where(
                PlatformOTPToken.email == norm,
                PlatformOTPToken.purpose == OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
            )
        )
        assert row is not None
        assert row.login_challenge_id is None


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_admin_unlock_pending_forces_one_otp_then_resumes_normal_login():
    """Simulates unlock: mandate row forces step-up once even when password-fail streak is cleared."""
    slug = f"lc_unl_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, fixed_otp)

    norm = normalize_auth_email(email)
    async with AsyncSessionLocal() as adb:
        tenant = await adb.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug))
        assert tenant is not None
        tid = int(tenant.id)
        await set_login_step_up_pending_after_unlock(adb, tid, norm)
        assert await login_step_up_pending_after_unlock_exists(adb, tid, norm) is True

    origin = f"http://{_host(tenant_slug)}"
    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert lr.status_code == 403, lr.text
    challenge_id = lr.json().get("login_challenge_id")
    assert challenge_id and len(challenge_id) == 36

    otp_plain = generate_otp()
    with patch("app.services.login_step_up_otp.send_otp_email_for_purpose", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            ir = await ac.post("/api/v1/auth/login-step-up/issue", json={"login_challenge_id": challenge_id})
    assert ir.status_code == 200, ir.text

    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformOTPToken).where(
                PlatformOTPToken.login_challenge_id == challenge_id,
                PlatformOTPToken.purpose == OTPPurpose.LOGIN_STEP_UP.value,
                PlatformOTPToken.consumed_at.is_(None),
            )
        )
        assert row is not None
        row.otp_hash = hash_otp(otp_plain)
        await adb.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        vr = await ac.post(
            "/api/v1/auth/login-step-up/verify",
            json={"login_challenge_id": challenge_id, "otp": otp_plain},
        )
    assert vr.status_code == 200, vr.json() == {"ok": True}

    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            ok = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "login_challenge_id": challenge_id},
            )
    assert ok.status_code == 200, ok.text

    async with AsyncSessionLocal() as adb:
        assert await login_step_up_pending_after_unlock_exists(adb, tid, norm) is False

    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            again = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert again.status_code == 200, again.text
    assert again.json().get("ok") is True
