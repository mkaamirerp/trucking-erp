"""Regression: integration scope teardown reports cleanup failures."""

from __future__ import annotations

import os
from unittest.mock import patch

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
from tests.support.integration_test_resources import (
    IntegrationCleanupError,
    IntegrationTestScope,
    _cleanup_load_rows,
    integration_scope_context,
)


def _integration_db_configured() -> bool:
    try:
        tenant_url = require_integration_tenant_database_url(context="teardown_errors_precheck")
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


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_teardown_raises_integration_cleanup_error(
    client: AsyncClient, override_auth_tenant
) -> None:
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="teardown_raise")
    await scope.activate()
    scope.tracker.track_load(101)
    scope.tracker.track_load(202)

    attempts: list[int] = []

    async def flaky_cleanup(db, tenant_id, load_id, *, context):
        attempts.append(int(load_id))
        if load_id == 101:
            raise RuntimeError("simulated load 101 cleanup failure")
        await _cleanup_load_rows(db, tenant_id, load_id, context=context)

    with patch(
        "tests.support.integration_test_resources._cleanup_load_rows",
        side_effect=flaky_cleanup,
    ):
        with pytest.raises(IntegrationCleanupError) as raised:
            await scope.teardown()

    assert attempts == [202, 101]
    assert len(raised.value.failures) == 1
    failure = raised.value.failures[0]
    assert failure.resource_type == "load"
    assert failure.resource_id == 101
    assert "simulated load 101" in str(failure.error)


@pytest.mark.skipif(SKIP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
async def test_teardown_continues_after_individual_cleanup_failure(
    client: AsyncClient, override_auth_tenant
) -> None:
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="teardown_continue")
    await scope.activate()
    scope.tracker.track_trip(9001)
    scope.tracker.track_load(9002)

    trip_calls: list[int] = []
    load_calls: list[int] = []

    async def flaky_trip(db, tenant_id, trip_id, *, context):
        trip_calls.append(int(trip_id))
        raise RuntimeError("trip cleanup failed")

    async def flaky_load(db, tenant_id, load_id, *, context):
        load_calls.append(int(load_id))
        await _cleanup_load_rows(db, tenant_id, load_id, context=context)

    with (
        patch(
            "tests.support.integration_test_resources._cleanup_trip_rows",
            side_effect=flaky_trip,
        ),
        patch(
            "tests.support.integration_test_resources._cleanup_load_rows",
            side_effect=flaky_load,
        ),
    ):
        with pytest.raises(IntegrationCleanupError) as raised:
            await scope.teardown()

    assert trip_calls == [9001]
    assert load_calls == [9002]
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
async def test_test_failure_preserved_when_teardown_also_fails(
    client: AsyncClient, override_auth_tenant
) -> None:
    async def always_fail_load(db, tenant_id, load_id, *, context):
        raise RuntimeError("teardown cleanup failed")

    with patch(
        "tests.support.integration_test_resources._cleanup_load_rows",
        side_effect=always_fail_load,
    ):
        with pytest.raises(RuntimeError, match="original test failure") as raised:
            async with integration_scope_context(
                client, AUTH_HEADERS, "teardown_preserve_test_failure"
            ) as scope:
                scope.tracker.track_load(1)
                raise RuntimeError("original test failure")

    notes = getattr(raised.value, "__notes__", [])
    assert any("Integration teardown also failed" in note for note in notes)
