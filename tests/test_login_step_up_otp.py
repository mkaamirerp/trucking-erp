"""Login step-up OTP: platform_otp_tokens purpose login_step_up + tenant binding (platform DB)."""
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
from app.utils.auth_identity import normalize_auth_email
from app.utils.otp import generate_otp, hash_otp
from tests.test_tenant_auth_matrix import _fake_provision_tenant_db, _host

SKIP_NO_DB = not os.environ.get("DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_login_step_up_issue_and_verify_returns_proof():
    slug = f"lsu_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        with (
            patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock),
            patch("app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock),
            patch("app.routers.public_signup.send_otp_email", new_callable=AsyncMock),
            patch("app.routers.public_signup.generate_otp", return_value=fixed_otp),
        ):
            r = await ac.post(
                "/api/v1/public/signup",
                json={
                    "workspace_slug": slug,
                    "email": email,
                    "password": password,
                    "first_name": "L",
                    "last_name": "SUO",
                    "phone": "+15551234567",
                    "company_legal_name": "LSU Inc",
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
                json={"email": email, "otp": fixed_otp, "signup_id": signup_id},
            )
        assert vr.status_code == 200, vr.text
        tenant_slug = vr.json().get("slug")
        assert tenant_slug

    origin = f"http://{_host(tenant_slug)}"
    norm = normalize_auth_email(email)
    async with AsyncSessionLocal() as adb:
        tid = int((await adb.scalar(select(PlatformTenant.id).where(PlatformTenant.slug == tenant_slug))) or 0)
        assert tid

    with patch("app.services.login_step_up_otp.send_otp_email_for_purpose", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            ir = await ac.post("/api/v1/auth/login-step-up/issue", json={"email": email})
    assert ir.status_code == 200, ir.text
    assert ir.json().get("ok") is True

    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformOTPToken).where(
                PlatformOTPToken.tenant_id == tid,
                PlatformOTPToken.email == norm,
                PlatformOTPToken.purpose == OTPPurpose.LOGIN_STEP_UP.value,
            )
        )
        assert row is not None
        assert row.consumed_at is None

    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        bad = await ac.post(
            "/api/v1/auth/login-step-up/verify",
            json={"email": email, "otp": "000000"},
        )
        assert bad.status_code == 401
        assert bad.json() == {"detail": "Invalid email or password"}

    otp_plain = None
    async with AsyncSessionLocal() as adb:
        r2 = await adb.scalar(
            select(PlatformOTPToken).where(
                PlatformOTPToken.tenant_id == tid,
                PlatformOTPToken.email == norm,
                PlatformOTPToken.purpose == OTPPurpose.LOGIN_STEP_UP.value,
                PlatformOTPToken.consumed_at.is_(None),
            )
        )
        otp_plain = generate_otp()
        r2.otp_hash = hash_otp(otp_plain)
        await adb.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        ok = await ac.post(
            "/api/v1/auth/login-step-up/verify",
            json={"email": email, "otp": otp_plain},
        )
    assert ok.status_code == 200, ok.text
    assert ok.json().get("proof_token")


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_login_requires_proof_when_setting_enabled():
    slug = f"lsu2_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        with (
            patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock),
            patch("app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock),
            patch("app.routers.public_signup.send_otp_email", new_callable=AsyncMock),
            patch("app.routers.public_signup.generate_otp", return_value=fixed_otp),
        ):
            r = await ac.post(
                "/api/v1/public/signup",
                json={
                    "workspace_slug": slug,
                    "email": email,
                    "password": password,
                    "first_name": "L",
                    "last_name": "SU2",
                    "phone": "+15551234567",
                    "company_legal_name": "LSU2 Inc",
                    "address": {
                        "street": "1 St",
                        "city": "Toronto",
                        "region": "ON",
                        "postal": "M5V 1A1",
                        "country": "CA",
                    },
                },
            )
        signup_id = r.json().get("signup_id")
        with patch("app.routers.public_signup.provision_tenant_db", AsyncMock(side_effect=_fake_provision_tenant_db)):
            vr = await ac.post(
                "/api/v1/public/verify-otp",
                json={"email": email, "otp": fixed_otp, "signup_id": signup_id},
            )
        tenant_slug = vr.json().get("slug")

    origin = f"http://{_host(tenant_slug)}"
    norm = normalize_auth_email(email)
    async with AsyncSessionLocal() as adb:
        tid = int((await adb.scalar(select(PlatformTenant.id).where(PlatformTenant.slug == tenant_slug))) or 0)

    otp_plain = generate_otp()
    with patch("app.services.login_step_up_otp.send_otp_email_for_purpose", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            await ac.post("/api/v1/auth/login-step-up/issue", json={"email": email})

    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformOTPToken).where(
                PlatformOTPToken.tenant_id == tid,
                PlatformOTPToken.email == norm,
                PlatformOTPToken.purpose == OTPPurpose.LOGIN_STEP_UP.value,
                PlatformOTPToken.consumed_at.is_(None),
            )
        )
        row.otp_hash = hash_otp(otp_plain)
        await adb.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        vr2 = await ac.post(
            "/api/v1/auth/login-step-up/verify",
            json={"email": email, "otp": otp_plain},
        )
    proof = vr2.json().get("proof_token")
    assert proof

    with patch.object(settings, "login_step_up_otp_required", True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            no_proof = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
    assert no_proof.status_code == 401
    assert no_proof.json() == {"detail": "Invalid email or password"}

    with patch.object(settings, "login_step_up_otp_required", True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            with_proof = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "login_step_up_proof": proof},
            )
    assert with_proof.status_code == 200, with_proof.text
    assert with_proof.json().get("ok") is True


@pytest.mark.asyncio
async def test_login_step_up_issue_rejected_on_apex_host():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        r = await ac.post("/api/v1/auth/login-step-up/issue", json={"email": "x@example.com"})
    assert r.status_code == 403
    assert r.json().get("detail") == "Use your company sign-in URL to continue."
