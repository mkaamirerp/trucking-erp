"""Regression: fleet fixture tracking, safe teardown, no cross-trip FK nulling."""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
os.environ.setdefault("TEST_BYPASS_AUTH", "1")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_fleet_fixtures import api_create_integration_fleet_bundle
from tests.support.integration_isolation import (
    AUTH_HEADERS,
    database_name_from_url,
    integration_tenant_db_name,
    require_integration_tenant_database_url,
)
from tests.support.integration_test_resources import (
    IntegrationCleanupError,
    IntegrationFleetDependencyError,
    IntegrationTestScope,
    integration_scope_context,
)


def _integration_db_configured() -> bool:
    try:
        tenant_url = require_integration_tenant_database_url(context="fleet_cleanup_precheck")
    except IntegrationIsolationError:
        return False
    return database_name_from_url(tenant_url) == integration_tenant_db_name()


SKIP = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "") or not _integration_db_configured()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant():
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


async def _driver_row_exists(scope: IntegrationTestScope, driver_id: int) -> bool:
    engine = create_async_engine(to_async_pg_url(scope.tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as db:
            n = await db.scalar(
                text("select count(*) from drivers where tenant_id=:t and id=:i"),
                {"t": scope.tenant_id, "i": int(driver_id)},
            )
            return int(n or 0) > 0
    finally:
        await engine.dispose()


async def _first_trip_driver_assignment(
    scope: IntegrationTestScope,
) -> tuple[int, int | None] | None:
    """Return (trip_id, driver_id) for an existing trip row, if any."""
    engine = create_async_engine(to_async_pg_url(scope.tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as db:
            row = await db.execute(
                text(
                    "select id, driver_id from trips where tenant_id=:t order by id asc limit 1"
                ),
                {"t": scope.tenant_id},
            )
            one = row.first()
            if one is None:
                return None
            return int(one[0]), one[1] if one[1] is not None else None
    finally:
        await engine.dispose()


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
@pytest.mark.asyncio
async def test_fleet_bundle_partial_failure_tracks_and_teardown_cleans_driver_truck(
    client: AsyncClient, override_auth_tenant
) -> None:
    """Driver/truck tracked before trailer create; teardown removes them if trailer fails."""
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="fleet_partial_fail")
    await scope.activate()
    driver_id = 0
    truck_id = 0
    real_post = client.post

    async def post_side_effect(url, **kwargs):
        if "/trailers" in str(url):
            return Response(400, json={"detail": "simulated trailer create failure"})
        return await real_post(url, **kwargs)

    with patch.object(client, "post", new=AsyncMock(side_effect=post_side_effect)):
        with pytest.raises(AssertionError, match="create trailer failed"):
            await api_create_integration_fleet_bundle(
                client, AUTH_HEADERS, f"P-FAIL-{uuid.uuid4().hex[:6]}", tracker=scope.tracker
            )

    assert scope.tracker.driver_ids
    assert scope.tracker.truck_ids
    assert not scope.tracker.trailer_ids
    driver_id = scope.tracker.driver_ids[0]
    truck_id = scope.tracker.truck_ids[0]
    assert await _driver_row_exists(scope, driver_id)

    await scope.teardown()
    verify = IntegrationTestScope(client, AUTH_HEADERS, context="fleet_partial_fail_verify")
    await verify.activate()
    assert not await _driver_row_exists(verify, driver_id)
    engine = create_async_engine(to_async_pg_url(verify.tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as db:
            n = await db.scalar(
                text("select count(*) from trucks where tenant_id=:t and id=:i"),
                {"t": verify.tenant_id, "i": truck_id},
            )
            assert int(n or 0) == 0
    finally:
        await engine.dispose()


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
@pytest.mark.asyncio
async def test_teardown_fails_when_untracked_trip_references_test_driver(
    client: AsyncClient, override_auth_tenant
) -> None:
    scope = IntegrationTestScope(client, AUTH_HEADERS, context="fleet_untracked_trip")
    await scope.activate()
    d0, t0, r0 = await api_create_integration_fleet_bundle(
        client, AUTH_HEADERS, f"UNTR-{uuid.uuid4().hex[:6]}", tracker=scope.tracker
    )
    tr = await client.post(
        "/api/v1/trips",
        headers=AUTH_HEADERS,
        json={"status": "planned", "job_type": "freight_load", "load_ids": []},
    )
    assert tr.status_code == 201
    untracked_trip_id = int(tr.json()["id"])
    asg = await client.put(
        f"/api/v1/trips/{untracked_trip_id}/assignment",
        headers=AUTH_HEADERS,
        json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
    )
    assert asg.status_code == 200

    with pytest.raises(IntegrationCleanupError) as raised:
        await scope.teardown()

    assert any(
        isinstance(f.error, IntegrationFleetDependencyError)
        for f in raised.value.failures
    )
    dep = next(
        f.error
        for f in raised.value.failures
        if isinstance(f.error, IntegrationFleetDependencyError)
    )
    assert dep.asset_kind == "driver"
    assert dep.asset_id == d0
    assert untracked_trip_id in dep.blocking_trip_ids

    # Cleanup untracked trip so tenant_pytest is not left polluted for other tests.
    engine = create_async_engine(to_async_pg_url(scope.tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as db:
            await db.execute(
                text("delete from trip_loads where tenant_id=:t and trip_id=:i"),
                {"t": scope.tenant_id, "i": untracked_trip_id},
            )
            await db.execute(
                text("delete from trips where tenant_id=:t and id=:i"),
                {"t": scope.tenant_id, "i": untracked_trip_id},
            )
            await db.commit()
    finally:
        await engine.dispose()
    await scope.teardown()


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
@pytest.mark.asyncio
async def test_fleet_teardown_does_not_clear_preexisting_trip_driver_assignment(
    client: AsyncClient, override_auth_tenant
) -> None:
    peer: tuple[int, int | None] | None = None
    async with integration_scope_context(client, AUTH_HEADERS, "fleet_peer_safe") as scope:
        peer = await _first_trip_driver_assignment(scope)
        if peer is None:
            pytest.skip("no pre-existing trips in tenant_pytest")
        peer_trip_id, peer_driver_before = peer

        d0, t0, r0 = await scope.create_fleet_bundle(f"PEER-{uuid.uuid4().hex[:6]}")
        tr = await scope.post_planned_trip([])
        assert tr.status_code == 201
        trip_id = int(tr.json()["id"])
        asg = await scope.client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert asg.status_code == 200

    verify = IntegrationTestScope(client, AUTH_HEADERS, context="fleet_peer_safe_verify")
    await verify.activate()
    engine = create_async_engine(to_async_pg_url(verify.tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as db:
            row = await db.execute(
                text("select driver_id from trips where tenant_id=:t and id=:i"),
                {"t": verify.tenant_id, "i": peer_trip_id},
            )
            peer_driver_after = row.scalar()
    finally:
        await engine.dispose()

    assert peer_driver_after == peer_driver_before
    assert not await _driver_row_exists(verify, d0)
