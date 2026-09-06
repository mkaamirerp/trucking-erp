"""Focused tests: integration isolation gate (never mutate tenant_demo / demo)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.integration_db_guard import (
    IntegrationIsolationError,
    assert_environment_allows_integration_mutation,
    assert_integration_db_name_allowed,
    assert_integration_host_allowed,
    assert_integration_tenant_slug_allowed,
    assert_tenant_database_url_allowed,
    database_name_from_url,
)
from tests.support.integration_isolation import (
    assert_mutating_integration_allowed,
    require_integration_tenant_database_url,
)
from tests.support.legacy_dispatch_test_seed import seed_load_dispatched_legacy_state


class TestIntegrationDbGuardUnit:
    def test_database_name_from_url_strips_path(self) -> None:
        assert database_name_from_url("postgresql://u:p@host:5432/tenant_demo") == "tenant_demo"
        assert database_name_from_url("postgresql+asyncpg://u:p@h/tenant_pytest") == "tenant_pytest"

    def test_tenant_demo_url_fails(self) -> None:
        with pytest.raises(IntegrationIsolationError, match="tenant_demo"):
            assert_tenant_database_url_allowed(
                "postgresql://u:p@db:5432/tenant_demo", context="unit"
            )

    def test_production_environment_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(IntegrationIsolationError, match="production"):
            assert_environment_allows_integration_mutation(context="unit")

    def test_demo_slug_fails(self) -> None:
        with pytest.raises(IntegrationIsolationError, match="demo"):
            assert_integration_tenant_slug_allowed("demo", context="unit")

    def test_demo_host_fails(self) -> None:
        with pytest.raises(IntegrationIsolationError, match="demo"):
            assert_integration_host_allowed("demo.truckerp.me", context="unit")

    def test_pytest_db_and_host_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "test")
        assert_environment_allows_integration_mutation(context="unit")
        assert_integration_db_name_allowed("tenant_pytest", context="unit")
        assert_integration_tenant_slug_allowed("pytest", context="unit")
        assert_integration_host_allowed("pytest.truckerp.me", context="unit")
        assert_tenant_database_url_allowed(
            "postgresql://u:p@db:5432/tenant_pytest", context="unit"
        )

    def test_require_url_rejects_demo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("TENANT_DATABASE_URL", "postgresql://u:p@db:5432/tenant_demo")
        with pytest.raises(IntegrationIsolationError, match="tenant_demo"):
            require_integration_tenant_database_url(context="unit")

    def test_require_url_accepts_pytest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("TENANT_DATABASE_URL", "postgresql://u:p@db:5432/tenant_pytest")
        assert "tenant_pytest" in require_integration_tenant_database_url(context="unit")


@pytest.mark.asyncio
async def test_seed_helper_cannot_bypass_with_demo_tenant_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TENANT_DATABASE_URL", "postgresql://u:p@db:5432/tenant_demo")

    db = AsyncMock()
    with pytest.raises(IntegrationIsolationError, match="tenant_demo"):
        await seed_load_dispatched_legacy_state(db, tenant_id=53, load_id=1)
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_seed_helper_rejects_demo_tenant_id_even_with_pytest_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TENANT_DATABASE_URL", "postgresql://u:p@db:5432/tenant_pytest")

    fake_tenant = MagicMock()
    fake_tenant.slug = "demo"
    fake_tenant.db_name = "tenant_demo"

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.scalar = AsyncMock(return_value=fake_tenant)

    with patch("app.core.database.AsyncSessionLocal", return_value=session):
        db = AsyncMock()
        with pytest.raises(IntegrationIsolationError, match="demo"):
            await seed_load_dispatched_legacy_state(db, tenant_id=53, load_id=1)
        db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_asgi_test_bypass_rejects_demo_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """TEST_BYPASS_AUTH + Host demo.truckerp.me must not resolve to tenant 53."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    monkeypatch.delenv("TENANT_DATABASE_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_TENANT_DATABASE_URL", raising=False)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/loads?page=1&size=1", headers={"host": "demo.truckerp.me"})
    assert r.status_code == 403
    body = r.json()
    assert body.get("code") == "INTEGRATION_ISOLATION_FORBIDDEN_TENANT"
    assert "Integration isolation" in str(body.get("detail"))

