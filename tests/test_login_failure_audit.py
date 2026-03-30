"""platform_login_failure_events rows on failed POST /auth/login (platform DB)."""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.platform import PlatformLoginFailureEvent, PlatformTenant
from app.services.login_failure_audit import (
    LOGIN_FAIL_NO_PLATFORM_USER,
    LOGIN_FAIL_VERIFY_PLATFORM_PASSWORD,
    email_fingerprint,
)
from app.utils.auth_identity import normalize_auth_email
from tests.test_tenant_auth_matrix import _fake_provision_tenant_db, _host

SKIP_NO_DB = not os.environ.get("DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_failed_login_persists_audit_row_wrong_platform_password():
    slug = f"lfaud_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612088"

    async with AsyncSessionLocal() as adb:
        mid = await adb.scalar(select(func.max(PlatformLoginFailureEvent.id)))
        mid = int(mid or 0)

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
                    "last_name": "FailAudit",
                    "phone": "+15551234567",
                    "company_legal_name": "L FailAudit Inc",
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
        assert signup_id
        with patch("app.routers.public_signup.provision_tenant_db", AsyncMock(side_effect=_fake_provision_tenant_db)):
            vr = await ac.post(
                "/api/v1/public/verify-otp",
                json={"email": email, "otp": fixed_otp, "signup_id": signup_id},
            )
        assert vr.status_code == 200, vr.text
        tenant_slug = vr.json().get("slug")
        assert tenant_slug

    async with AsyncSessionLocal() as adb:
        t = await adb.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug))
        assert t is not None
        tid = int(t.id)

    origin = f"http://{_host(tenant_slug)}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        bad = await ac.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "not-the-right-password"},
        )
    assert bad.status_code == 401, bad.text
    assert bad.json() == {"detail": "Invalid email or password"}

    fp = email_fingerprint(normalize_auth_email(email))
    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformLoginFailureEvent)
            .where(
                PlatformLoginFailureEvent.id > mid,
                PlatformLoginFailureEvent.tenant_id == tid,
                PlatformLoginFailureEvent.reason_code == LOGIN_FAIL_VERIFY_PLATFORM_PASSWORD,
                PlatformLoginFailureEvent.email_fingerprint == fp,
            )
            .order_by(PlatformLoginFailureEvent.id.desc())
            .limit(1)
        )
    assert row is not None


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_failed_login_persists_audit_row_no_platform_user():
    slug = f"lfghost_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    fixed_otp = "612089"

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
                    "first_name": "G",
                    "last_name": "Host",
                    "phone": "+15551234567",
                    "company_legal_name": "G Host Inc",
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

    async with AsyncSessionLocal() as adb:
        mid = await adb.scalar(select(func.max(PlatformLoginFailureEvent.id)))
        mid = int(mid or 0)
        t = await adb.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug))
        tid = int(t.id)

    ghost = f"noghost_{uuid.uuid4().hex[:8]}@example.com"
    gnorm = normalize_auth_email(ghost)
    gfp = email_fingerprint(gnorm)

    origin = f"http://{_host(tenant_slug)}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        bad = await ac.post(
            "/api/v1/auth/login",
            json={"email": ghost, "password": "whatever"},
        )
    assert bad.status_code == 401, bad.text
    assert bad.json() == {"detail": "Invalid email or password"}

    async with AsyncSessionLocal() as adb:
        row = await adb.scalar(
            select(PlatformLoginFailureEvent)
            .where(
                PlatformLoginFailureEvent.id > mid,
                PlatformLoginFailureEvent.tenant_id == tid,
                PlatformLoginFailureEvent.reason_code == LOGIN_FAIL_NO_PLATFORM_USER,
                PlatformLoginFailureEvent.email_fingerprint == gfp,
            )
            .order_by(PlatformLoginFailureEvent.id.desc())
            .limit(1)
        )
    assert row is not None
