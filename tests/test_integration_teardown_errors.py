"""Regression: integration scope teardown reports cleanup failures."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import (
    AUTH_HEADERS,
    database_name_from_url,
    integration_tenant_db_name,
    require_integration_tenant_database_url,
)
from tests.support.integration_test_resources import (
    IntegrationCleanupError,
    IntegrationTestScope,
    integration_scope_context,
)


def _integration_db_configured() -> bool:
    try:
        tenant_url = require_integration_tenant_database_url(context="teardown_errors_precheck")
    except IntegrationIsolationError:
        return False
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


async def _first_preexisting_load_id(scope: IntegrationTestScope) -> int | None:
    engine = create_async_engine(to_async_pg_url(scope.tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as db:
            return await db.scalar(
                text(
                    "select id from loads where tenant_id = :t order by id asc limit 1"
                ),
                {"t": scope.tenant_id},
            )
    finally:
        await engine.dispose()


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_teardown_raises_integration_cleanup_error(
    client: AsyncClient, override_auth_tenant
) -> None:
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="teardown_raise")
    await scope.activate()
    fail_id = 10_001
    ok_id = 10_002
    scope.tracker.track_load(fail_id)
    scope.tracker.track_load(ok_id)

    attempts: list[int] = []

    async def mock_cleanup(db, tenant_id, load_id, *, context):
        attempts.append(int(load_id))
        if load_id == fail_id:
            raise RuntimeError("simulated load cleanup failure")

    with patch(
        "tests.support.integration_test_resources._cleanup_load_rows",
        side_effect=mock_cleanup,
    ):
        with pytest.raises(IntegrationCleanupError) as raised:
            await scope.teardown()

    assert attempts == [ok_id, fail_id]
    assert len(raised.value.failures) == 1
    failure = raised.value.failures[0]
    assert failure.resource_type == "load"
    assert failure.resource_id == fail_id
    assert "simulated load cleanup failure" in str(failure.error)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_teardown_continues_after_individual_cleanup_failure(
    client: AsyncClient, override_auth_tenant
) -> None:
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="teardown_continue")
    await scope.activate()
    trip_id = 20_001
    load_id = 20_002
    scope.tracker.track_trip(trip_id)
    scope.tracker.track_load(load_id)

    trip_calls: list[int] = []
    load_calls: list[int] = []

    async def mock_trip(db, tenant_id, trip_id, *, context):
        trip_calls.append(int(trip_id))
        raise RuntimeError("trip cleanup failed")

    async def mock_load(db, tenant_id, load_id, *, context):
        load_calls.append(int(load_id))

    with (
        patch(
            "tests.support.integration_test_resources._cleanup_trip_rows",
            side_effect=mock_trip,
        ),
        patch(
            "tests.support.integration_test_resources._cleanup_load_rows",
            side_effect=mock_load,
        ),
    ):
        with pytest.raises(IntegrationCleanupError) as raised:
            await scope.teardown()

    assert trip_calls == [trip_id]
    assert load_calls == [load_id]
    assert any(f.resource_type == "trip" for f in raised.value.failures)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_teardown_success_does_not_raise(
    client: AsyncClient, override_auth_tenant
) -> None:
    load_id = 0
    async with integration_scope_context(client, AUTH_HEADERS, "teardown_success") as scope:
        load_id = await scope.create_ready_load_id("TEARDOWN-OK")
        assert await scope.load_row_exists(load_id)
    verifier = IntegrationTestScope(client, AUTH_HEADERS, context="teardown_success_verify")
    await verifier.activate()
    assert not await verifier.load_row_exists(load_id)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_real_cleanup_does_not_remove_untracked_loads(
    client: AsyncClient, override_auth_tenant
) -> None:
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="teardown_peer_safe")
    await scope.activate()
    peer_id = await _first_preexisting_load_id(scope)
    if peer_id is None:
        pytest.skip("no pre-existing loads in tenant_pytest to use as peer control")

    assert await scope.load_row_exists(int(peer_id))
    owned_id = await scope.create_ready_load_id("PEER-SAFE-OWNED")
    assert await scope.load_row_exists(owned_id)

    await scope.teardown()

    assert await scope.load_row_exists(int(peer_id))
    assert not await scope.load_row_exists(owned_id)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_test_failure_preserved_when_teardown_also_fails(
    client: AsyncClient, override_auth_tenant
) -> None:
    mock_cleanup = AsyncMock(side_effect=RuntimeError("teardown cleanup failed"))

    with patch(
        "tests.support.integration_test_resources._cleanup_load_rows",
        mock_cleanup,
    ):
        with pytest.raises(RuntimeError, match="original test failure") as raised:
            async with integration_scope_context(
                client, AUTH_HEADERS, "teardown_preserve_test_failure"
            ) as scope:
                _ = await scope.create_ready_load_id("PRESERVE-FAIL")
                raise RuntimeError("original test failure")

    notes = getattr(raised.value, "__notes__", [])
    assert any("Integration teardown also failed" in note for note in notes)
    mock_cleanup.assert_awaited()
