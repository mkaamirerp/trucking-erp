"""POST /trips/{id}/loads/{load_id}/final-delivery — I14 consignee custody closeout."""

from __future__ import annotations

import os
import uuid

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
from tests.support.demo_clone_integration import (
    clear_demo_clone_http_test_overrides,
    install_demo_clone_http_test_overrides,
)
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.custody_http import activate_via_custody, final_delivery
from tests.support.integration_test_resources import integration_scope_context

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
    async with integration_scope_context(client, AUTH_HEADERS, "trip_final_delivery_slice") as scope:
        yield scope


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> str:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200
    body = r0.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"F{uuid.uuid4().hex[:7].upper()}"
    r1 = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": prefix},
    )
    assert r1.status_code == 200, r1.text
    return prefix


async def _pick_load_ids(scope, n: int = 1) -> list[int]:
    return await scope.create_ready_load_ids(n, tag_prefix="TRIP-FDEL")


async def _assign_and_start(client: AsyncClient, trip_id: int, scope) -> None:
    d_id, t_id, r_id = await scope.create_fleet_bundle(f"FDEL-{uuid.uuid4().hex[:6]}")
    r = await client.put(
        f"/api/v1/trips/{trip_id}/assignment",
        headers=AUTH_HEADERS,
        json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
    )
    assert r.status_code == 200, r.text
    r2 = await client.post(
        f"/api/v1/trips/{trip_id}/execution-signal",
        headers=AUTH_HEADERS,
        json={"source": "dispatcher_manual"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS


async def _load_row(load_id: int) -> dict:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, active_trip_id, custody_owner, custody_trip_id "
                        "FROM loads WHERE id = :lid"
                    ),
                    {"lid": load_id},
                )
            ).mappings().first()
            assert row is not None
            return dict(row)
    finally:
        await engine.dispose()


async def _trip_load_row(trip_id: int, load_id: int) -> dict:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status_within_trip, completed_at, removed_at "
                        "FROM trip_loads WHERE trip_id = :tid AND load_id = :lid"
                    ),
                    {"tid": trip_id, "lid": load_id},
                )
            ).mappings().first()
            assert row is not None
            return dict(row)
    finally:
        await engine.dispose()


async def _count_events(load_id: int, event_type: str | None = None) -> int:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            if event_type:
                n = (
                    await session.execute(
                        text(
                            "SELECT count(*)::int FROM load_custody_events "
                            "WHERE load_id = :lid AND event_type = :et"
                        ),
                        {"lid": load_id, "et": event_type},
                    )
                ).scalar()
            else:
                n = (
                    await session.execute(
                        text("SELECT count(*)::int FROM load_custody_events WHERE load_id = :lid"),
                        {"lid": load_id},
                    )
                ).scalar()
            return int(n or 0)
    finally:
        await engine.dispose()


async def _force_trip_status(trip_id: int, status: str) -> None:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            await session.execute(
                text("UPDATE trips SET status = :st WHERE id = :tid"),
                {"tid": trip_id, "st": status},
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestTripFinalDeliverySlice:
    async def test_happy_path_then_trip_complete(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        before = await _load_row(load_id)

        r = await integration_scope.post_planned_trip([load_id])
        assert r.status_code == 201, r.text
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id, integration_scope)
        assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200

        r_fd = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"notes": "receiver signed"})
        assert r_fd.status_code == 200, r_fd.text
        body = r_fd.json()
        assert body["replayed"] is False
        assert body["snapshot"]["custody_owner"] == "delivered"
        assert body["snapshot"]["custody_trip_id"] is None
        assert body["membership_status_within_trip"] == "completed"
        assert body["event"]["event_type"] == "final_delivery"

        after = await _load_row(load_id)
        assert after["status"] == before["status"]
        assert after["custody_owner"] == "delivered"
        assert after["active_trip_id"] is None
        tl = await _trip_load_row(trip_id, load_id)
        assert tl["status_within_trip"] == "completed"
        assert tl["completed_at"] is not None

        trip_det = await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)
        assert trip_det.status_code == 200
        assert trip_det.json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS

        r_done = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r_done.status_code == 200, r_done.text
        assert r_done.json()["status"] == TRIP_CONTAINER_STATUS_COMPLETED

    async def test_retry_idempotent_no_duplicate_events(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        r = await integration_scope.post_planned_trip([load_id])
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id, integration_scope)
        assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200

        key = f"fd-{uuid.uuid4().hex}"
        r1 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key})
        assert r1.status_code == 200, r1.text
        ev1 = int(r1.json()["event"]["id"])
        n1 = await _count_events(load_id, "final_delivery")

        r2 = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key})
        assert r2.status_code == 200, r2.text
        assert r2.json()["replayed"] is True
        assert int(r2.json()["event"]["id"]) == ev1
        n2 = await _count_events(load_id, "final_delivery")
        assert n2 == n1

    async def test_wrong_trip_rejected(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        r_a = await integration_scope.post_planned_trip([load_id])
        trip_a = int(r_a.json()["id"])
        await _assign_and_start(client, trip_a, integration_scope)
        assert (await activate_via_custody(client, AUTH_HEADERS, trip_a, load_id)).status_code == 200

        r_b = await integration_scope.post_planned_trip([])
        trip_b = int(r_b.json()["id"])
        await _assign_and_start(client, trip_b, integration_scope)

        r_no_mem = await final_delivery(client, AUTH_HEADERS, trip_b, load_id)
        assert r_no_mem.status_code == 404
        assert r_no_mem.json()["detail"]["code"] == "TRIP_LOAD_NOT_FOUND"

        url = _tenant_async_url()
        assert url
        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                await session.execute(
                    text("UPDATE loads SET custody_trip_id = :wrong WHERE id = :lid"),
                    {"wrong": trip_b, "lid": load_id},
                )
                await session.commit()
        finally:
            await engine.dispose()

        r_bad = await final_delivery(client, AUTH_HEADERS, trip_a, load_id)
        assert r_bad.status_code == 409
        assert r_bad.json()["detail"]["code"] == "CUSTODY_SNAPSHOT_MISMATCH"

    async def test_planned_membership_rejected(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        r = await integration_scope.post_planned_trip([load_id])
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id, integration_scope)

        r_bad = await final_delivery(client, AUTH_HEADERS, trip_id, load_id)
        assert r_bad.status_code == 409
        assert r_bad.json()["detail"]["code"] == "MEMBERSHIP_NOT_ACTIVE"

    async def test_not_in_progress_trip_rejected(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        r = await integration_scope.post_planned_trip([load_id])
        trip_id = int(r.json()["id"])
        d_id, t_id, r_id = await integration_scope.create_fleet_bundle(f"FDEL-AS-{uuid.uuid4().hex[:6]}")
        assert (
            await client.put(
                f"/api/v1/trips/{trip_id}/assignment",
                headers=AUTH_HEADERS,
                json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
            )
        ).status_code == 200
        assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200

        r_bad = await final_delivery(client, AUTH_HEADERS, trip_id, load_id)
        assert r_bad.status_code == 409
        assert r_bad.json()["detail"]["code"] == "INVALID_TRIP_STATUS_FOR_FINAL_DELIVERY"

    async def test_cancelled_trip_rejected(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        r = await integration_scope.post_planned_trip([load_id])
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id, integration_scope)
        assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200
        await _force_trip_status(trip_id, "cancelled")

        r_bad = await final_delivery(client, AUTH_HEADERS, trip_id, load_id)
        assert r_bad.status_code == 409
        assert r_bad.json()["detail"]["code"] == "TRIP_CANCELLED"

    async def test_already_completed_membership_409_without_valid_retry(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        r = await integration_scope.post_planned_trip([load_id])
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id, integration_scope)
        assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200
        assert (await final_delivery(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200

        r_dup = await final_delivery(client, AUTH_HEADERS, trip_id, load_id, body={"notes": "again"})
        assert r_dup.status_code == 200
        assert r_dup.json()["replayed"] is True

    async def test_failed_attempt_no_event_rollback(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        r = await integration_scope.post_planned_trip([load_id])
        trip_id = int(r.json()["id"])
        d_id, t_id, r_id = await integration_scope.create_fleet_bundle(f"FDEL-RB-{uuid.uuid4().hex[:6]}")
        assert (
            await client.put(
                f"/api/v1/trips/{trip_id}/assignment",
                headers=AUTH_HEADERS,
                json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
            )
        ).status_code == 200
        assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200

        n_before = await _count_events(load_id, "final_delivery")
        r_fail = await final_delivery(
            client,
            AUTH_HEADERS,
            trip_id,
            load_id,
            body={"idempotency_key": f"rollback-{uuid.uuid4().hex}"},
        )
        assert r_fail.status_code == 409
        assert r_fail.json()["detail"]["code"] == "INVALID_TRIP_STATUS_FOR_FINAL_DELIVERY"
        n_after = await _count_events(load_id, "final_delivery")
        assert n_after == n_before
        tl = await _trip_load_row(trip_id, load_id)
        assert tl["status_within_trip"] == "active"

    async def test_multi_load_other_membership_unchanged(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        loads = await _pick_load_ids(integration_scope, 2)
        if len(loads) < 2:
            pytest.skip("need two loads")
        load_a, load_b = loads[0], loads[1]
        r = await integration_scope.post_planned_trip([load_a, load_b])
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id, integration_scope)
        for lid in (load_a, load_b):
            assert (await activate_via_custody(client, AUTH_HEADERS, trip_id, lid)).status_code == 200

        assert (await final_delivery(client, AUTH_HEADERS, trip_id, load_a)).status_code == 200
        tl_a = await _trip_load_row(trip_id, load_a)
        tl_b = await _trip_load_row(trip_id, load_b)
        assert tl_a["status_within_trip"] == "completed"
        assert tl_b["status_within_trip"] == "active"
        assert (await _load_row(load_b))["active_trip_id"] == trip_id

        r_block = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r_block.status_code == 409
        assert r_block.json()["detail"]["code"] == "OPEN_ACTIVE_MEMBERSHIP_REMAINS"
