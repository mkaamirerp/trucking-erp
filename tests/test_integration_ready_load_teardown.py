"""Regression: tracked integration Loads are removed after scope teardown."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.core.integration_db_guard import IntegrationIsolationError
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import (
    AUTH_HEADERS,
    integration_tenant_db_name,
    require_integration_tenant_database_url,
)
from tests.support.integration_ready_load import (
    api_create_draft_load,
    api_mark_load_ready,
)
from tests.support.integration_test_resources import (
    IntegrationTestScope,
    integration_scope_context,
)


def _integration_db_configured() -> bool:
    try:
        tenant_url = require_integration_tenant_database_url(context="ready_load_teardown_precheck")
    except IntegrationIsolationError:
        return False
    from tests.support.integration_isolation import database_name_from_url

    return database_name_from_url(tenant_url) == integration_tenant_db_name()


_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
SKIP = _PLACEHOLDER_PLATFORM_DB or not _integration_db_configured()


@pytest.fixture
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


async def _assert_load_absent(client: AsyncClient, load_id: int) -> None:
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="ready_load_teardown_verify")
    await scope.activate()
    assert not await scope.load_row_exists(load_id)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_tracked_ready_load_removed_after_scope_teardown(
    client: AsyncClient, override_auth_tenant
) -> None:
    load_id = 0
    async with integration_scope_context(client, AUTH_HEADERS, "ready_load_teardown") as scope:
        load_id = await scope.create_ready_load_id("TEARDOWN-REG")
        assert await scope.load_row_exists(load_id)
    await _assert_load_absent(client, load_id)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_draft_tracked_and_removed_when_mark_ready_fails(
    client: AsyncClient, override_auth_tenant
) -> None:
    load_id = 0
    async with integration_scope_context(client, AUTH_HEADERS, "mark_ready_fail_teardown") as scope:
        draft = await api_create_draft_load(
            scope.client,
            scope.headers,
            "MR-FAIL",
            tracker=scope.tracker,
        )
        load_id = int(draft["id"])
        assert await scope.load_row_exists(load_id)
        with pytest.raises(AssertionError, match="mark-ready failed"):
            await api_mark_load_ready(scope.client, scope.headers, draft)
    await _assert_load_absent(client, load_id)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_tracked_load_removed_when_test_raises(
    client: AsyncClient, override_auth_tenant
) -> None:
    load_id = 0
    with pytest.raises(RuntimeError, match="simulated test failure"):
        async with integration_scope_context(
            client, AUTH_HEADERS, "teardown_on_test_exception"
        ) as scope:
            load_id = await scope.create_ready_load_id("TEARDOWN-ON-RAISE")
            assert await scope.load_row_exists(load_id)
            raise RuntimeError("simulated test failure")
    await _assert_load_absent(client, load_id)
