"""Cross-tenant: valid JWT must not work against another workspace Host (403)."""
from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.platform import PlatformTenant, PlatformUser, TenantMembership
from app.utils.jwt_auth import create_access_token

REQUIRES_DB = not os.environ.get("DATABASE_URL")


def _host_for_slug(slug: str) -> str:
    base = (settings.base_domain or "truckerp.me").lower()
    return f"{slug}.{base}"


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.asyncio
async def test_bearer_wrong_tenant_claim_vs_host_returns_403() -> None:
    """JWT tenant_id does not match Host-resolved tenant → 403 (get_current_user)."""
    async with AsyncSessionLocal() as db:
        demo = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == "demo").limit(1))
        if not demo:
            pytest.skip("No platform tenant slug=demo")
        other = await db.scalar(
            select(PlatformTenant)
            .where(PlatformTenant.slug != "demo", PlatformTenant.status == "ACTIVE")
            .limit(1)
        )
        if not other:
            pytest.skip("Need a second ACTIVE tenant (not demo)")
        m = await db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == demo.id,
                TenantMembership.status == "active",
            ).limit(1)
        )
        if not m:
            pytest.skip("Need an active TenantMembership on demo")
        user_id = m.user_id
        pu = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id)))
        sv = int(getattr(pu, "session_version", 1) or 1) if pu else 1

    token = create_access_token(
        user_id=user_id,
        tenant_id=int(other.id),
        tenant_slug=other.slug,
        roles=["TENANT_ADMIN"],
        sv=sv,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "host": _host_for_slug("demo"),
            },
        )
    assert r.status_code == 403
    assert "host" in str(r.json().get("detail", "")).lower() or "workspace" in str(r.json().get("detail", "")).lower()


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.asyncio
async def test_bearer_correct_tenant_token_wrong_host_no_membership_returns_403() -> None:
    """Token for tenant A on Host B where user has no access → middleware membership 403."""
    async with AsyncSessionLocal() as db:
        demo = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == "demo").limit(1))
        other = await db.scalar(
            select(PlatformTenant)
            .where(PlatformTenant.slug != "demo", PlatformTenant.status == "ACTIVE")
            .limit(1)
        )
        if not demo or not other:
            pytest.skip("Need demo and another ACTIVE tenant")
        m = await db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == demo.id,
                TenantMembership.status == "active",
            ).limit(1)
        )
        if not m:
            pytest.skip("Need demo membership")
        other_member = await db.scalar(
            select(TenantMembership).where(
                TenantMembership.user_id == m.user_id,
                TenantMembership.tenant_id == other.id,
                TenantMembership.status == "active",
            ).limit(1)
        )
        if other_member:
            pytest.skip("User has both-tenant access; pick a narrower fixture user")

        user_id = m.user_id
        pu = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id)))
        sv = int(getattr(pu, "session_version", 1) or 1) if pu else 1

    token = create_access_token(
        user_id=user_id,
        tenant_id=int(demo.id),
        tenant_slug=demo.slug,
        roles=["TENANT_ADMIN"],
        sv=sv,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "host": _host_for_slug(other.slug),
            },
        )
    assert r.status_code == 403
    detail = str(r.json().get("detail", "")).lower()
    assert "tenant" in detail or "access" in detail


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.asyncio
async def test_cookie_access_token_wrong_tenant_claim_vs_host_returns_403() -> None:
    """access_token cookie: mismatched tenant claim vs Host → 403 (same as Bearer)."""
    async with AsyncSessionLocal() as db:
        demo = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == "demo").limit(1))
        other = await db.scalar(
            select(PlatformTenant)
            .where(PlatformTenant.slug != "demo", PlatformTenant.status == "ACTIVE")
            .limit(1)
        )
        if not demo or not other:
            pytest.skip("Need demo and another ACTIVE tenant")
        m = await db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == demo.id,
                TenantMembership.status == "active",
            ).limit(1)
        )
        if not m:
            pytest.skip("Need demo membership")
        user_id = m.user_id
        pu = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id)))
        sv = int(getattr(pu, "session_version", 1) or 1) if pu else 1
        token = create_access_token(
            user_id=user_id,
            tenant_id=int(other.id),
            tenant_slug=other.slug,
            roles=["TENANT_ADMIN"],
            sv=sv,
        )
        demo_slug = demo.slug

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/api/v1/auth/me",
            headers={
                "host": _host_for_slug(demo_slug),
                "Cookie": f"access_token={token}",
            },
        )
    assert r.status_code == 403
    d = str(r.json().get("detail", "")).lower()
    assert "host" in d or "workspace" in d
