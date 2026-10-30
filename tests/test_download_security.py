"""Tests for download endpoint tenant isolation and forbidden access."""
from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

REQUIRES_DB = not os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    # ASGITransport: requests share the test's event loop (no per-request portal loop) and the
    # app lifespan/background sweepers are not started.
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def authed_tenant_admin():
    from app.main import app
    from tests.support.integration_auth import (
        clear_current_user_and_tenant_overrides,
        install_host_aligned_current_user_and_tenant,
    )

    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


class TestCompanySetupDocumentTenantIsolation:
    """GET /api/v1/public/company-setup/document must enforce tenant isolation."""

    async def test_forbidden_when_key_prefix_mismatch(self, client) -> None:
        """Requesting demo's key while Host is another workspace must return 403."""
        storage_key = "demo/company_docs/company/53/abc123.pdf"
        resp = await client.get(
            f"/api/v1/public/company-setup/document?storage_key={storage_key}",
            headers={"host": "acme.truckerp.me"},
        )
        assert resp.status_code == 403
        assert "not valid for tenant" in resp.json().get("detail", "").lower()

    async def test_400_when_no_tenant(self, client) -> None:
        """Request without tenant (no subdomain, no header) must return 400."""
        storage_key = "demo/company_docs/company/53/abc123.pdf"
        resp = await client.get(
            f"/api/v1/public/company-setup/document?storage_key={storage_key}",
        )
        assert resp.status_code == 400
        assert "tenant" in resp.json().get("detail", "").lower()


class TestPayDocumentTenantIsolation:
    """GET /api/v1/payroll/documents/{id}/download must return doc only for owning tenant."""

    @pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
    async def test_404_when_doc_not_owned_by_tenant(self, client, authed_tenant_admin) -> None:
        """Authenticated tenant admin: a document id outside this tenant is not found (no existence leak)."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.core.db_url import to_async_pg_url

        raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
        if not raw:
            pytest.skip("tenant DB URL required")
        engine = create_async_engine(to_async_pg_url(raw))
        try:
            async with engine.connect() as conn:
                installed = await conn.scalar(text("SELECT to_regclass('public.pay_documents') IS NOT NULL"))
        finally:
            await engine.dispose()
        if not installed:
            pytest.xfail("STOP-GATE: pay_documents is not installed in this tenant schema (ORM/DB drift)")
        resp = await client.get(
            "/api/v1/payroll/documents/999999991/download",
            headers={"host": "pytest.truckerp.me"},
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
    async def test_401_without_authentication(self, client) -> None:
        from app.main import app

        assert not app.dependency_overrides
        resp = await client.get(
            "/api/v1/payroll/documents/999999991/download",
            headers={"host": "pytest.truckerp.me"},
        )
        assert resp.status_code == 401, resp.text


class TestApplicantFileTenantIsolation:
    """Applicant file endpoints must resolve tenant from token and reject cross-tenant access."""

    @pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
    async def test_404_with_invalid_token(self, client) -> None:
        """Invalid or expired token returns 404."""
        resp = await client.get(
            "/api/v1/driver-onboarding/applicant/application/file",
            params={"token": "invalid-token-xyz", "file_id": "any"},
            headers={"host": "pytest.truckerp.me"},
        )
        assert resp.status_code == 404
