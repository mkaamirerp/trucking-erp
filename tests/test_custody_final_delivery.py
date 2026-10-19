"""Per-Load final delivery. Does not complete the Trip or change Load.status."""

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

from app.main import app
from tests.support.demo_clone_integration import (
    clear_demo_clone_http_test_overrides,
    install_demo_clone_http_test_overrides,
)
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_test_resources import integration_scope_context

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "pytest.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")


def _tenant_async_url() -> str:
    from app.core.db_url import to_async_pg_url

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    assert raw
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
    async with integration_scope_context(client, AUTH_HEADERS, "final_delivery") as scope:
        yield scope


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> str:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200
    body = r0.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"D{uuid.uuid4().hex[:7].upper()}"
    r1 = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": prefix},
    )
    assert r1.status_code == 200, r1.text
    return prefix


async def _rows(sql: str, params: dict) -> list[dict]:
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            result = await session.execute(text(sql), params)
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


async def _exec(sql: str, params: dict) -> None:
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            await session.execute(text(sql), params)
            await session.commit()
    finally:
        await engine.dispose()


async def _assign(client: AsyncClient, scope, trip_id: int) -> None:
    driver_id, truck_id, trailer_id = await scope.create_fleet_bundle(f"fd{trip_id}")
    assigned = await client.put(
        f"/api/v1/trips/{trip_id}/assignment",
        headers=AUTH_HEADERS,
        json={"driver_id": driver_id, "truck_id": truck_id, "trailer_id": trailer_id},
    )
    assert assigned.status_code == 200, assigned.text


async def _start(client: AsyncClient, trip_id: int) -> None:
    started = await client.post(
        f"/api/v1/trips/{trip_id}/execution-signal",
        headers=AUTH_HEADERS,
        json={"source": "dispatcher_manual"},
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"


async def _accept(client: AsyncClient, trip_id: int, load_id: int) -> None:
    response = await client.post(
        f"/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody",
        headers=AUTH_HEADERS,
        json={},
    )
    assert response.status_code == 200, response.text


def _detail_code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


async def _stop_times(load_id: int) -> list[tuple]:
    rows = await _rows(
        "SELECT id, arrived_at, departed_at FROM load_stops WHERE load_id = :lid ORDER BY id",
        {"lid": load_id},
    )
    return [(row["id"], row["arrived_at"], row["departed_at"]) for row in rows]


async def _delivery_count(load_id: int) -> int:
    rows = await _rows(
        "SELECT count(*)::int AS n FROM load_custody_events WHERE load_id = :lid AND event_type = 'final_delivery'",
        {"lid": load_id},
    )
    return int(rows[0]["n"])


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestFinalDelivery:
    async def test_two_loads_deliver_separately_then_complete_trip(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        load_a, load_b = await integration_scope.create_ready_load_ids(2, tag_prefix="FINAL-DELIVERY")
        status_a = (await _rows("SELECT status FROM loads WHERE id = :lid", {"lid": load_a}))[0]["status"]
        status_b = (await _rows("SELECT status FROM loads WHERE id = :lid", {"lid": load_b}))[0]["status"]
        stops_a = await _stop_times(load_a)
        stops_b = await _stop_times(load_b)

        created = await integration_scope.post_planned_trip([load_a, load_b])
        assert created.status_code == 201, created.text
        trip_id = int(created.json()["id"])
        await _assign(client, integration_scope, trip_id)
        await _start(client, trip_id)
        await _accept(client, trip_id, load_a)
        await _accept(client, trip_id, load_b)

        body = {"idempotency_key": f"deliver-{load_a}", "notes": "receiver signed"}
        first = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/final-delivery",
            headers=AUTH_HEADERS,
            json=body,
        )
        assert first.status_code == 200, first.text
        delivered = first.json()
        assert delivered["replayed"] is False
        assert delivered["trip_status"] == "in_progress"
        assert delivered["load_status"] == status_a
        assert delivered["membership_status_within_trip"] == "completed"
        assert delivered["active_trip_id"] is None
        assert delivered["snapshot"]["custody_owner"] == "delivered"
        assert delivered["snapshot"]["custody_trip_id"] is None
        assert delivered["snapshot"]["custody_terminal_id"] is None
        assert delivered["snapshot"]["custody_trailer_id"] is None
        assert delivered["event"]["event_type"] == "final_delivery"
        assert delivered["event"]["notes"] == "receiver signed"
        assert delivered["event"]["idempotency_key"] == body["idempotency_key"]
        assert delivered["event"]["trip_id"] == trip_id

        replay = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/final-delivery",
            headers=AUTH_HEADERS,
            json=body,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["event"]["id"] == delivered["event"]["id"]
        assert await _delivery_count(load_a) == 1

        assert (await _rows("SELECT status, active_trip_id FROM loads WHERE id = :lid", {"lid": load_b}))[0][
            "active_trip_id"
        ] == trip_id
        membership_b = await _rows(
            "SELECT status_within_trip FROM trip_loads WHERE trip_id = :tid AND load_id = :lid",
            {"tid": trip_id, "lid": load_b},
        )
        assert membership_b[0]["status_within_trip"] == "active"
        blocked = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert blocked.status_code == 409
        assert _detail_code(blocked) == "OPEN_ACTIVE_MEMBERSHIP_REMAINS"

        outbound = await integration_scope.post_planned_trip([load_a])
        assert outbound.status_code == 201, outbound.text
        outbound_id = int(outbound.json()["id"])

        second = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_b}/final-delivery",
            headers=AUTH_HEADERS,
            json={"idempotency_key": f"deliver-{load_b}"},
        )
        assert second.status_code == 200, second.text
        assert second.json()["load_status"] == status_b
        assert second.json()["trip_status"] == "in_progress"

        closed = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert closed.status_code == 200, closed.text
        assert closed.json()["status"] == "completed"
        assert (await client.get(f"/api/v1/trips/{outbound_id}", headers=AUTH_HEADERS)).json()["status"] == "planned"
        assert (await _rows("SELECT status FROM loads WHERE id = :lid", {"lid": load_a}))[0]["status"] == status_a
        assert (await _rows("SELECT status FROM loads WHERE id = :lid", {"lid": load_b}))[0]["status"] == status_b
        assert await _stop_times(load_a) == stops_a
        assert await _stop_times(load_b) == stops_b

    async def test_terminal_and_unknown_custody_are_rejected(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        load_unknown, load_terminal = await integration_scope.create_ready_load_ids(2, tag_prefix="FINAL-REJECT")
        created = await integration_scope.post_planned_trip([load_unknown, load_terminal])
        assert created.status_code == 201, created.text
        trip_id = int(created.json()["id"])
        await _assign(client, integration_scope, trip_id)
        await _accept(client, trip_id, load_unknown)
        too_early = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_unknown}/final-delivery",
            headers=AUTH_HEADERS,
            json={},
        )
        assert too_early.status_code == 409
        assert _detail_code(too_early) == "INVALID_TRIP_STATUS_FOR_FINAL_DELIVERY"

        await _start(client, trip_id)
        await _accept(client, trip_id, load_terminal)
        await _exec(
            "UPDATE loads SET custody_owner = 'unknown', custody_trip_id = NULL WHERE id = :lid",
            {"lid": load_unknown},
        )
        unknown = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_unknown}/final-delivery",
            headers=AUTH_HEADERS,
            json={},
        )
        assert unknown.status_code == 409
        assert _detail_code(unknown) == "CUSTODY_SNAPSHOT_MISMATCH"

        await _exec(
            "UPDATE loads SET custody_owner = 'terminal', custody_trip_id = NULL WHERE id = :lid",
            {"lid": load_terminal},
        )
        terminal = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_terminal}/final-delivery",
            headers=AUTH_HEADERS,
            json={},
        )
        assert terminal.status_code == 409
        assert _detail_code(terminal) == "CUSTODY_SNAPSHOT_MISMATCH"
        assert await _delivery_count(load_unknown) == 0
        assert await _delivery_count(load_terminal) == 0
        assert (await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)).json()["status"] == "in_progress"

    async def test_idempotency_same_key_replays_different_key_does_not(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        load_id = (await integration_scope.create_ready_load_ids(1, tag_prefix="FINAL-KEY"))[0]
        created = await integration_scope.post_planned_trip([load_id])
        assert created.status_code == 201, created.text
        trip_id = int(created.json()["id"])
        await _assign(client, integration_scope, trip_id)
        await _start(client, trip_id)
        accept_key = f"accept-{load_id}"
        accepted = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody",
            headers=AUTH_HEADERS,
            json={"idempotency_key": accept_key},
        )
        assert accepted.status_code == 200, accepted.text

        delivery_key = f"deliver-{load_id}"
        first = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/final-delivery",
            headers=AUTH_HEADERS,
            json={"idempotency_key": delivery_key, "notes": "signed"},
        )
        assert first.status_code == 200, first.text
        event_id = first.json()["event"]["id"]
        assert await _delivery_count(load_id) == 1

        replay = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/final-delivery",
            headers=AUTH_HEADERS,
            json={"idempotency_key": delivery_key, "notes": "signed again"},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["event"]["id"] == event_id
        assert replay.json()["membership_status_within_trip"] == "completed"
        assert replay.json()["snapshot"]["custody_owner"] == "delivered"
        assert replay.json()["trip_status"] == "in_progress"
        assert await _delivery_count(load_id) == 1

        other_key = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/final-delivery",
            headers=AUTH_HEADERS,
            json={"idempotency_key": f"deliver-other-{load_id}"},
        )
        assert other_key.status_code == 409, other_key.text
        assert _detail_code(other_key) == "IDEMPOTENCY_KEY_CONFLICT"
        assert await _delivery_count(load_id) == 1
        assert (await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)).json()["status"] == "in_progress"

        reused = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/final-delivery",
            headers=AUTH_HEADERS,
            json={"idempotency_key": accept_key},
        )
        assert reused.status_code == 409, reused.text
        assert _detail_code(reused) == "IDEMPOTENCY_KEY_CONFLICT"
        assert await _delivery_count(load_id) == 1
        row = (await _rows("SELECT custody_owner, status, active_trip_id FROM loads WHERE id = :lid", {"lid": load_id}))[0]
        assert row["custody_owner"] == "delivered"
        assert row["active_trip_id"] is None
