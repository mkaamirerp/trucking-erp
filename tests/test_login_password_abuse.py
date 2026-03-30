"""Platform DB login password failure streaks + Turnstile gate (after threshold)."""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import settings
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.platform import PlatformLoginPasswordFailStreak, PlatformTenant
from app.services.login_failure_audit import email_fingerprint
from app.utils.auth_identity import normalize_auth_email
from tests.test_tenant_auth_matrix import _fake_provision_tenant_db, _host

SKIP_NO_DB = not os.environ.get("DATABASE_URL")


async def _signup_and_verify_tenant(ac: AsyncClient, slug: str, email: str, password: str, otp: str) -> str:
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
                "last_name": "Abuse",
                "phone": "+15551234567",
                "company_legal_name": "Abuse Inc",
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
async def test_after_three_password_failures_turnstile_required_when_secret_set():
    slug = f"lpab_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_and_verify_tenant(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        for _ in range(3):
            bad = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
            )
            assert bad.status_code == 401, bad.text
            assert bad.json() == {"detail": "Invalid email or password"}

        with patch.object(settings, "turnstile_secret_key", "test-secret-key"):
            gated = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
            )
        assert gated.status_code == 403, gated.text
        assert gated.json() == {"detail": "Additional verification required."}


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_fourth_attempt_with_turnstile_proceeds_to_password_check():
    slug = f"lpab2_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_and_verify_tenant(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        for _ in range(3):
            await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})

        with (
            patch.object(settings, "turnstile_secret_key", "test-secret-key"),
            patch(
                "app.services.login_password_abuse.verify_turnstile_token",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            still_bad = await ac.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": "still-wrong",
                    "turnstile_token": "dummy-token",
                },
            )
        assert still_bad.status_code == 401, still_bad.text
        assert still_bad.json() == {"detail": "Invalid email or password"}


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_streak_row_tracks_failures_per_tenant():
    slug = f"lpab3_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_and_verify_tenant(ac, slug, email, password, otp)

    async with AsyncSessionLocal() as adb:
        t = await adb.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug))
        tid = int(t.id)
        fp = email_fingerprint(normalize_auth_email(email))

    origin = f"http://{_host(tenant_slug)}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        for _ in range(3):
            await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})

    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformLoginPasswordFailStreak).where(
                PlatformLoginPasswordFailStreak.tenant_id == tid,
                PlatformLoginPasswordFailStreak.email_fingerprint == fp,
            )
        )
        assert row is not None
        assert int(row.streak_count) == 3
