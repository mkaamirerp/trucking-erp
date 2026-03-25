"""
Mock integration test: full flow from signup → dashboard (and legacy verify_otp → dashboard).

Runs without a browser. Requires DATABASE_URL; skips if unset.

To run with a real database (e.g. local Postgres):
  export DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
  pytest tests/test_signup_to_dashboard_flow.py -v

Flows covered:
- Single-step signup: POST /signup (with mocked provision_tenant_db) → GET /api/v1/auth/me.
- Legacy: seed tenant+user+OTP, POST /verify-otp (mocked provision) → GET /api/v1/auth/me.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import (
    OTPPurpose,
    PlatformOTPToken,
    PlatformSubscription,
    PlatformTenant,
    PlatformTenantMember,
    PlatformUser,
    SubscriptionPlan,
    SubscriptionStatus,
    TenantDBStatus,
    TenantStatus,
)
from app.utils.otp import get_otp_expiration, hash_otp
from app.utils.password import hash_password

# Skip when DATABASE_URL is not set (e.g. CI without Postgres)
SKIP_NO_DB = not os.environ.get("DATABASE_URL")


async def _fake_provision_tenant_db(tenant_id: int, db: AsyncSession, *, activate: bool = True):
    """Update tenant to READY/ACTIVE without running real CREATE DATABASE or alembic."""
    result = await db.execute(
        select(PlatformTenant).where(PlatformTenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.db_status = TenantDBStatus.READY.value
    tenant.db_name = tenant.db_name or f"tenant_{tenant.slug.replace('-', '_')}"
    if activate:
        tenant.status = TenantStatus.ACTIVE.value
    tenant.provisioned_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required for signup flow test")
def test_single_step_signup_then_dashboard(client):
    """Single-step signup: POST /signup (mock provision) → GET /api/v1/auth/me (cookies)."""
    slug_suffix = uuid.uuid4().hex[:8]
    workspace_slug = f"flowtest_{slug_suffix}"
    email = f"flowtest_{slug_suffix}@example.com"
    # Mock provisioning so we don't run CREATE DATABASE / alembic
    with patch(
        "app.routers.public_signup.provision_tenant_db",
        AsyncMock(side_effect=_fake_provision_tenant_db),
    ):
        # Mock email so we don't send real mail
        with patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock), patch(
            "app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock
        ):
            payload = {
                "workspace_slug": workspace_slug,
                "email": email,
                "password": "password123456",
                "first_name": "Flow",
                "last_name": "Test",
                "phone": "+15551234567",
                "company_legal_name": "Flow Test Inc",
                "address": {
                    "street": "123 Test St",
                    "city": "Toronto",
                    "region": "ON",
                    "postal": "M5V 1A1",
                    "country": "CA",
                },
            }
            # Signup must be on main domain, not tenant subdomain
            response = client.post(
                "/api/v1/public/signup",
                json=payload,
                headers={"host": "truckerp.me"},
            )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data.get("success") is True
    tenant_slug = data.get("tenant_slug")
    assert tenant_slug
    assert "redirect_url" in data
    assert tenant_slug in data["redirect_url"]

    # Cookies set (session)
    cookies = response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies

    # Simulate dashboard: GET /api/v1/auth/me with same client (cookies sent)
    me_response = client.get("/api/v1/auth/me", headers={"host": "truckerp.me"})
    assert me_response.status_code == 200, me_response.text
    me_data = me_response.json()
    assert me_data.get("email") == email
    assert me_data.get("tenant_slug") == tenant_slug
    assert me_data.get("tenant_id") is not None


@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required for verify_otp flow test")
def test_verify_otp_then_dashboard(client, app):
    """Legacy flow: pre-seed tenant+user+OTP → POST /verify-otp → GET /api/v1/auth/me."""
    from app.core.database import AsyncSessionLocal

    otp_slug = f"otptest_{uuid.uuid4().hex[:8]}"
    otp_email = f"otptest_{uuid.uuid4().hex[:8]}@example.com"

    # Seed: tenant (PENDING_SETUP, NOT_CREATED), user, membership, subscription, OTP
    async def seed():
        async with AsyncSessionLocal() as db:
            tenant = PlatformTenant(
                name="Otp Test Tenant",
                slug=otp_slug,
                status=TenantStatus.PENDING_SETUP.value,
                db_status=TenantDBStatus.NOT_CREATED.value,
            )
            db.add(tenant)
            await db.flush()
            user = PlatformUser(
                first_name="Otp",
                last_name="User",
                email=otp_email,
                password_hash=hash_password("password1234"),
                is_email_verified=False,
                status="ACTIVE",
            )
            db.add(user)
            await db.flush()
            db.add(PlatformTenantMember(tenant_id=tenant.id, platform_user_id=user.id, role="TENANT_ADMIN"))
            db.add(
                PlatformSubscription(
                    tenant_id=tenant.id,
                    plan=SubscriptionPlan.TRIAL.value,
                    status=SubscriptionStatus.TRIAL_ACTIVE.value,
                )
            )
            otp_code = "123456"
            otp_row = PlatformOTPToken(
                purpose=OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
                email=user.email,
                user_id=user.id,
                otp_hash=hash_otp(otp_code),
                expires_at=get_otp_expiration(),
            )
            db.add(otp_row)
            await db.commit()
            return tenant.id, user.email, otp_code

    import asyncio
    tenant_id, email, otp_code = asyncio.run(seed())

    # Mock provisioning for verify_otp path
    with patch(
        "app.routers.public_signup.provision_tenant_db",
        AsyncMock(side_effect=_fake_provision_tenant_db),
    ):
        with patch("app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock):
            response = client.post(
                "/api/v1/public/verify-otp",
                json={"email": email, "otp": otp_code},
                headers={"host": "truckerp.me"},
            )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("verified") is True
    assert "workspace_url" in data
    assert "access_token" in response.cookies

    me_response = client.get("/api/v1/auth/me", headers={"host": "truckerp.me"})
    assert me_response.status_code == 200, me_response.text
    assert me_response.json().get("email") == email


@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required for Bearer /me test")
def test_login_then_me_with_bearer_token(client):
    """Login returns access_token in JSON; GET /api/v1/me with Authorization: Bearer <token> succeeds."""
    slug_suffix = uuid.uuid4().hex[:8]
    workspace_slug = f"beartest_{slug_suffix}"
    email = f"beartest_{slug_suffix}@example.com"
    password = "password123456"
    with patch(
        "app.routers.public_signup.provision_tenant_db",
        AsyncMock(side_effect=_fake_provision_tenant_db),
    ):
        with patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock), patch(
            "app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock
        ):
            signup_resp = client.post(
                "/api/v1/public/signup",
                json={
                    "workspace_slug": workspace_slug,
                    "email": email,
                    "password": password,
                    "first_name": "Bear",
                    "last_name": "Test",
                    "phone": "+15551234567",
                    "company_legal_name": "Bear Test Inc",
                    "address": {
                        "street": "123 Test St",
                        "city": "Toronto",
                        "region": "ON",
                        "postal": "M5V 1A1",
                        "country": "CA",
                    },
                },
                headers={"host": "truckerp.me"},
            )
    assert signup_resp.status_code == 201, signup_resp.text
    tenant_slug = signup_resp.json().get("tenant_slug")
    assert tenant_slug

    # Login to get access_token in response body (no cookies used for the next request)
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"host": f"{tenant_slug}.truckerp.me"},
    )
    assert login_resp.status_code == 200, login_resp.text
    login_data = login_resp.json()
    access_token = login_data.get("access_token")
    assert access_token, "login must return access_token for API/Bearer clients"

    # GET /api/v1/me with Bearer token only (no cookies)
    me_resp = client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {access_token}",
            "host": f"{tenant_slug}.truckerp.me",
        },
    )
    assert me_resp.status_code == 200, me_resp.text
    me_data = me_resp.json()
    assert me_data.get("tenant_slug") == tenant_slug
    assert me_data.get("tenant_id") is not None
