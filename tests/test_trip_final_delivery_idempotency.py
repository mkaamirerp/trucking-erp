"""Final-delivery idempotency regressions (I14 correction)."""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.trip_dispatch import TRIP_CONTAINER_STATUS_COMPLETED, TRIP_CONTAINER_STATUS_IN_PROGRESS
from app.main import app
from tests.support.custody_http import activate_via_custody, final_delivery
from tests.support.demo_clone_integration import (
    clear_demo_clone_http_test_overrides,
    demo_clone_active,
    demo_clone_tenant_id,
    install_demo_clone_http_test_overrides,
)
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
    install_mutable_tenant_current_user_and_tenant,
)
from tests.support.integration_test_resources import integration_scope_context
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "pytest.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")


def _tenant_async_url() -> str | None:
    from app.core.db_url import to_async_pg_url

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


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
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    install_demo_clone_http_test_overrides(app)
    yield
    clear_current_user_and_tenant_overrides(app)
    clear_demo_clone_http_test_overrides(app)


@pytest.fixture
async def integration_scope(client, override_auth_tenant):
    async with integration_scope_context(client, AUTH_HEADERS, "trip_final_delivery_idem") as scope:
        yield scope


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> str:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200
    body = r0.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"I{uuid.uuid4().hex[:7].upper()}"
    r1 = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": prefix},
    )
    assert r1.status_code == 200, r1.text
    return prefix


async def _assign_and_start(client: AsyncClient, trip_id: int, scope) -> None:
    d_id, t_id, r_id = await scope.create_fleet_bundle(f"IDEM-{uuid.uuid4().hex[:6]}")
    assert (
        await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
    ).status_code == 200
    r2 = await client.post(
        f"/api/v1/trips/{trip_id}/execution-signal",
        headers=AUTH_HEADERS,
        json={"source": "dispatcher_manual"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS


async def _ready_trip_with_active_load(client, scope) -> tuple[int, int]:
    load_id = int((await scope.create_ready_load_ids(1, tag_prefix="FD-IDEM"))[0])
    r = await scope.post_planned_trip([load_id])
    assert r.status_code == 201, r.text
    trip_id = int(r.json()["id"])
    await _assign_and_start(client, trip_id, scope)
    assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200
    return trip_id, load_id


async def _count_events(load_id: int, event_type: str) -> int:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            n = (
                await session.execute(
                    text(
                        "SELECT count(*)::int FROM load_custody_events "
                        "WHERE load_id = :lid AND event_type = :et"
                    ),
                    {"lid": load_id, "et": event_type},
                )
            ).scalar()
            return int(n or 0)
    finally:
        await engine.dispose()


async def _trip_status(trip_id: int) -> str:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text("SELECT status FROM trips WHERE id = :tid"),
                    {"tid": trip_id},
                )
            ).scalar()
            assert row is not None
            return str(row)
    finally:
        await engine.dispose()


async def _load_custody(load_id: int) -> dict:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT custody_owner, custody_trip_id FROM loads WHERE id = :lid"
                    ),
                    {"lid": load_id},
                )
            ).mappings().one()
            return dict(row)
    finally:
        await engine.dispose()


async def _membership_status(trip_id: int, load_id: int) -> str:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status_within_trip FROM trip_loads "
                        "WHERE trip_id = :tid AND load_id = :lid"
                    ),
                    {"tid": trip_id, "lid": load_id},
                )
            ).scalar()
            assert row is not None
            return str(row)
    finally:
        await engine.dispose()


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestFinalDeliveryIdempotencyRegression:
    async def test_same_key_replay(self, client: AsyncClient, locked_prefix: str, integration_scope):
        trip_id, load_id = await _ready_trip_with_active_load(client, integration_scope)
        key = f"idem-{uuid.uuid4().hex}"
        r1 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key})
        assert r1.status_code == 200 and r1.json()["replayed"] is False
        ev = int(r1.json()["event"]["id"])
        r2 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key})
        assert r2.status_code == 200 and r2.json()["replayed"] is True
        assert int(r2.json()["event"]["id"]) == ev

    async def test_different_key_conflict(self, client: AsyncClient, locked_prefix: str, integration_scope):
        trip_id, load_id = await _ready_trip_with_active_load(client, integration_scope)
        key1 = f"k1-{uuid.uuid4().hex}"
        key2 = f"k2-{uuid.uuid4().hex}"
        assert (
            await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key1})
        ).status_code == 200
        r = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key2})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
        assert await _count_events(load_id, "final_delivery") == 1

    async def test_no_key_state_replay(self, client: AsyncClient, locked_prefix: str, integration_scope):
        trip_id, load_id = await _ready_trip_with_active_load(client, integration_scope)
        r1 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={})
        assert r1.status_code == 200
        n = await _count_events(load_id, "final_delivery")
        r2 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={})
        assert r2.status_code == 200 and r2.json()["replayed"] is True
        assert await _count_events(load_id, "final_delivery") == n

    async def test_no_key_delivery_rejects_new_key_on_replay(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        trip_id, load_id = await _ready_trip_with_active_load(client, integration_scope)
        assert (await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={})).status_code == 200
        r = await final_delivery(
            client,
            AUTH_HEADERS,
            trip_id,
            load_id,
            body={"idempotency_key": f"late-{uuid.uuid4().hex}"},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    async def test_replay_after_trip_completed(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        trip_id, load_id = await _ready_trip_with_active_load(client, integration_scope)
        key = f"post-complete-{uuid.uuid4().hex}"
        r1 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key})
        assert r1.status_code == 200
        n = await _count_events(load_id, "final_delivery")
        assert (
            await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        ).status_code == 200
        assert await _trip_status(trip_id) == TRIP_CONTAINER_STATUS_COMPLETED

        r2 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key})
        assert r2.status_code == 200 and r2.json()["replayed"] is True
        assert await _count_events(load_id, "final_delivery") == n
        assert await _trip_status(trip_id) == TRIP_CONTAINER_STATUS_COMPLETED

        r3 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={})
        assert r3.status_code == 200 and r3.json()["replayed"] is True
        assert await _trip_status(trip_id) == TRIP_CONTAINER_STATUS_COMPLETED

    async def test_cross_tenant_request_rejected(
        self, client: AsyncClient, locked_prefix: str, integration_scope, test_bypass_env
    ):
        trip_id, load_id = await _ready_trip_with_active_load(client, integration_scope)
        real_tid = (
            demo_clone_tenant_id()
            if demo_clone_active()
            else await platform_tenant_id_for_slug("pytest")
        )
        holder = {"tenant_id": real_tid}
        install_mutable_tenant_current_user_and_tenant(app, holder)
        try:
            holder["tenant_id"] = real_tid + 9_999_999
            r = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={})
            assert r.status_code == 404
        finally:
            clear_current_user_and_tenant_overrides(app)
            install_host_aligned_current_user_and_tenant(app)
            install_demo_clone_http_test_overrides(app)

    async def test_membership_complete_failure_rolls_back_custody(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        trip_id, load_id = await _ready_trip_with_active_load(client, integration_scope)
        n0 = await _count_events(load_id, "final_delivery")
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as soft_client:
            with patch(
                "app.services.load_custody_transitions._complete_trip_load_membership_locked",
                new_callable=AsyncMock,
            ) as mock_complete:
                mock_complete.side_effect = RuntimeError("membership complete failed")
                r = await final_delivery(soft_client, AUTH_HEADERS, trip_id, load_id, body={})
        assert r.status_code == 500
        assert await _count_events(load_id, "final_delivery") == n0
        snap = await _load_custody(load_id)
        assert snap["custody_owner"] == "trip"
        assert int(snap["custody_trip_id"]) == trip_id
        assert await _membership_status(trip_id, load_id) == "active"
