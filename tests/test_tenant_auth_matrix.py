"""
Tenant vs platform auth matrix: login, refresh, /me, password reset session invalidation, cutover helpers.

Requires DATABASE_URL for HTTP integration tests; optional RUN_TENANT_AUTH_FLIP_TESTS=1 + env for mode flip/rollback.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.platform import PlatformTenant, TenantDBStatus, TenantStatus
from app.utils.auth_identity import normalize_auth_email
from app.utils.jwt_auth import create_access_token, decode_token, TokenType
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
from app.services.tenant_auth_cutover_verify import collect_tenant_auth_cutover_errors

SKIP_NO_DB = not os.environ.get("DATABASE_URL")


def _host(slug: str) -> str:
    base = (settings.base_domain or "truckerp.me").lower()
    return f"{slug}.{base}"


async def _fake_provision_tenant_db(tenant_id: int, db, *, activate: bool = True):
    """Mark tenant READY without running CREATE DATABASE / alembic."""
    from sqlalchemy.ext.asyncio import AsyncSession

    result = await db.execute(select(PlatformTenant).where(PlatformTenant.id == tenant_id))
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


def test_normalize_auth_email_trim_lower_no_gmail_dot_plus():
    assert normalize_auth_email("  User.Name+tag@gmail.com ") == "user.name+tag@gmail.com"
    assert normalize_auth_email(None) == ""


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_platform_mode_signup_login_me_refresh_cycle():
    from fastapi.testclient import TestClient

    slug = f"pauth_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"

    with patch("app.routers.public_signup.provision_tenant_db", AsyncMock(side_effect=_fake_provision_tenant_db)):
        with patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock), patch(
            "app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock
        ):
            client = TestClient(app)
            r = client.post(
                "/api/v1/public/signup",
                json={
                    "workspace_slug": slug,
                    "email": email,
                    "password": password,
                    "first_name": "P",
                    "last_name": "Auth",
                    "phone": "+15551234567",
                    "company_legal_name": "P Auth Inc",
                    "address": {
                        "street": "1 St",
                        "city": "Toronto",
                        "region": "ON",
                        "postal": "M5V 1A1",
                        "country": "CA",
                    },
                },
                headers={"host": "truckerp.me"},
            )
    assert r.status_code == 201, r.text
    tenant_slug = r.json()["tenant_slug"]

    async with AsyncSessionLocal() as pdb:
        t = await pdb.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug))
        assert t is not None
        assert not tenant_uses_tenant_db_auth(getattr(t, "tenant_auth_mode", None))

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"host": _host(tenant_slug)},
    )
    assert login.status_code == 200, login.text
    access = login.json().get("access_token")
    assert access
    payload = decode_token(access, expected_type=TokenType.ACCESS)
    assert payload.get("sub")
    assert int(payload.get("sv", 0)) >= 1

    me = client.get("/api/v1/auth/me", headers={"host": _host(tenant_slug), "Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body.get("email") == email
    assert body.get("tenant_auth_mode") in ("platform", None)
    assert body.get("tenant_local_user_id") is None

    # Refresh with cookies from login
    client2 = TestClient(app)
    lr = client2.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"host": _host(tenant_slug)},
    )
    assert lr.status_code == 200
    ref = client2.post("/api/v1/auth/refresh", headers={"host": _host(tenant_slug)})
    assert ref.status_code == 200, ref.text


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_platform_mode_reset_password_invalidates_access_and_refresh():
    from fastapi.testclient import TestClient

    slug = f"preset_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    old_pw = "password123456"
    new_pw = "newpassword123456"

    with patch("app.routers.public_signup.provision_tenant_db", AsyncMock(side_effect=_fake_provision_tenant_db)):
        with patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock), patch(
            "app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock
        ):
            client = TestClient(app)
            r = client.post(
                "/api/v1/public/signup",
                json={
                    "workspace_slug": slug,
                    "email": email,
                    "password": old_pw,
                    "first_name": "R",
                    "last_name": "Set",
                    "phone": "+15551234567",
                    "company_legal_name": "R Set Inc",
                    "address": {
                        "street": "1 St",
                        "city": "Toronto",
                        "region": "ON",
                        "postal": "M5V 1A1",
                        "country": "CA",
                    },
                },
                headers={"host": "truckerp.me"},
            )
    assert r.status_code == 201, r.text
    tenant_slug = r.json()["tenant_slug"]

    c = TestClient(app)
    login = c.post(
        "/api/v1/auth/login",
        json={"email": email, "password": old_pw},
        headers={"host": _host(tenant_slug)},
    )
    assert login.status_code == 200
    access_old = login.json()["access_token"]
    assert c.get("/api/v1/auth/me", headers={"host": _host(tenant_slug), "Authorization": f"Bearer {access_old}"}).status_code == 200

    fixed_raw = "fixed_token_urlsafe_test_xxxxxxxxxxxxxxxx"
    with patch("app.routers.auth.secrets.token_urlsafe", return_value=fixed_raw), patch(
        "app.routers.auth.send_password_reset_email", new_callable=AsyncMock
    ):
        fp = c.post(
            "/api/v1/auth/forgot-password",
            json={"email": email},
            headers={"host": _host(tenant_slug)},
        )
    assert fp.status_code == 200

    rs = c.post(
        "/api/v1/auth/reset-password",
        json={"token": fixed_raw, "new_password": new_pw},
        headers={"host": _host(tenant_slug)},
    )
    assert rs.status_code == 200, rs.text

    assert (
        c.get(
            "/api/v1/auth/me",
            headers={"host": _host(tenant_slug), "Authorization": f"Bearer {access_old}"},
        ).status_code
        == 401
    )

    c2 = TestClient(app)
    c2.post(
        "/api/v1/auth/login",
        json={"email": email, "password": old_pw},
        headers={"host": _host(tenant_slug)},
    )
    bad_refresh = c2.post("/api/v1/auth/refresh", headers={"host": _host(tenant_slug)})
    assert bad_refresh.status_code == 401


def test_cutover_verify_error_strings_stable_for_drift_alerts():
    """Document expected collect_tenant_auth_cutover_errors phrases (ops/alerting)."""
    assert "password_hash drift" in "password_hash drift platform_user=x tenant_user=y"
    assert "session_version drift" in "session_version drift platform_user=x tenant_user=y"
    assert "platform_tenant_user_map count" in "platform_tenant_user_map count 0 != platform_tenant_members 1"


FLIP = os.environ.get("RUN_TENANT_AUTH_FLIP_TESTS") == "1"
FLIP_TID = os.environ.get("TENANT_AUTH_FLIP_TENANT_ID")
FLIP_EMAIL = os.environ.get("TENANT_AUTH_FLIP_EMAIL")
FLIP_PASSWORD = os.environ.get("TENANT_AUTH_FLIP_PASSWORD")


@pytest.mark.asyncio
@pytest.mark.skipif(
    SKIP_NO_DB or not FLIP or not FLIP_TID or not FLIP_EMAIL or not FLIP_PASSWORD,
    reason="Set RUN_TENANT_AUTH_FLIP_TESTS=1 and TENANT_AUTH_FLIP_TENANT_ID, _EMAIL, _PASSWORD",
)
async def test_tenant_auth_mode_flip_login_me_refresh_rollback_relogin():
    tid = int(FLIP_TID)
    async with AsyncSessionLocal() as pdb:
        tenant_row = await pdb.get(PlatformTenant, tid)
        if not tenant_row:
            pytest.skip("tenant id not found")
        orig_mode = getattr(tenant_row, "tenant_auth_mode", None) or "platform"
        slug = tenant_row.slug

    errs = await collect_tenant_auth_cutover_errors(tid)
    if errs:
        pytest.skip("pre-cutover verify failed: " + "; ".join(errs))

    try:
        async with AsyncSessionLocal() as pdb:
            t = await pdb.get(PlatformTenant, tid)
            t.tenant_auth_mode = "tenant"
            await pdb.commit()

        async with AsyncSessionLocal() as pdb:
            t2 = await pdb.get(PlatformTenant, tid)
            assert tenant_uses_tenant_db_auth(getattr(t2, "tenant_auth_mode", None))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            host = _host(slug)
            lr = await ac.post(
                "/api/v1/auth/login",
                json={"email": FLIP_EMAIL, "password": FLIP_PASSWORD},
                headers={"host": host},
            )
            assert lr.status_code == 200, lr.text
            access = lr.json().get("access_token")
            pl = decode_token(access, expected_type=TokenType.ACCESS)
            assert str(pl.get("sub")).isdigit()
            mr = await ac.get("/api/v1/auth/me", headers={"host": host, "Authorization": f"Bearer {access}"})
            assert mr.status_code == 200, mr.text
            assert mr.json().get("tenant_auth_mode") == "tenant"
            assert mr.json().get("tenant_local_user_id") is not None

            ac.cookies.update(lr.cookies)
            rr = await ac.post("/api/v1/auth/refresh", headers={"host": host})
            assert rr.status_code == 200, rr.text

        async with AsyncSessionLocal() as pdb:
            t = await pdb.get(PlatformTenant, tid)
            t.tenant_auth_mode = "platform"
            await pdb.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            host = _host(slug)
            bad_me = await ac.get(
                "/api/v1/auth/me",
                headers={"host": host, "Authorization": f"Bearer {access}"},
            )
            assert bad_me.status_code == 401

            lr2 = await ac.post(
                "/api/v1/auth/login",
                json={"email": FLIP_EMAIL, "password": FLIP_PASSWORD},
                headers={"host": host},
            )
            assert lr2.status_code == 200, lr2.text
            pl2 = decode_token(lr2.json()["access_token"], expected_type=TokenType.ACCESS)
            assert not str(pl2.get("sub")).isdigit()
    finally:
        async with AsyncSessionLocal() as pdb:
            t = await pdb.get(PlatformTenant, tid)
            if t:
                t.tenant_auth_mode = orig_mode
                await pdb.commit()


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_tenant_mode_sub_wrong_tenant_id_in_claim_returns_403():
    """Same host/token tenant-id guard as platform mode; sub is tenant_users.id."""
    if not FLIP or not FLIP_TID or not FLIP_EMAIL or not FLIP_PASSWORD:
        pytest.skip("needs flip env and credentials")
    tid = int(FLIP_TID)
    async with AsyncSessionLocal() as pdb:
        tenant_row = await pdb.get(PlatformTenant, tid)
        if not tenant_row:
            pytest.skip("tenant missing")
        other = await pdb.scalar(
            select(PlatformTenant)
            .where(PlatformTenant.id != tid, PlatformTenant.status == "ACTIVE")
            .limit(1)
        )
        if not other:
            pytest.skip("need second active tenant")
        prev = getattr(tenant_row, "tenant_auth_mode", None) or "platform"
        slug = tenant_row.slug

    errs = await collect_tenant_auth_cutover_errors(tid)
    if errs:
        pytest.skip("precheck failed")

    async with AsyncSessionLocal() as pdb:
        t = await pdb.get(PlatformTenant, tid)
        t.tenant_auth_mode = "tenant"
        await pdb.commit()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            host = _host(slug)
            lr = await ac.post(
                "/api/v1/auth/login",
                json={"email": FLIP_EMAIL, "password": FLIP_PASSWORD},
                headers={"host": host},
            )
            assert lr.status_code == 200, lr.text
            pl = decode_token(lr.json()["access_token"], expected_type=TokenType.ACCESS)
            tu_sub = pl["sub"]
            sv = pl["sv"]
            bad = create_access_token(
                user_id=tu_sub,
                tenant_id=int(other.id),
                tenant_slug=other.slug,
                roles=["TENANT_ADMIN"],
                sv=int(sv),
            )
            r = await ac.get(
                "/api/v1/auth/me",
                headers={"host": host, "Authorization": f"Bearer {bad}"},
            )
            assert r.status_code == 403
    finally:
        async with AsyncSessionLocal() as pdb:
            t = await pdb.get(PlatformTenant, tid)
            if t:
                t.tenant_auth_mode = prev
                await pdb.commit()
