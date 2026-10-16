"""Stop arrival and departure. Does not change commercial stop sync, custody, or Trip completion."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.main import app
from app.models.tenant import AuditEvent
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
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def integration_scope(client, override_auth_tenant):
    async with integration_scope_context(client, AUTH_HEADERS, "stop_execution") as scope:
        yield scope


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> str:
    response = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"S{uuid.uuid4().hex[:7].upper()}"
    locked = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": prefix},
    )
    assert locked.status_code == 200, locked.text
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


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


async def _prepare(client: AsyncClient, scope, load_ids: list[int]) -> int:
    created = await scope.post_planned_trip(load_ids)
    assert created.status_code == 201, created.text
    trip_id = int(created.json()["id"])
    driver_id, truck_id, trailer_id = await scope.create_fleet_bundle(f"st{trip_id}")
    assigned = await client.put(
        f"/api/v1/trips/{trip_id}/assignment",
        headers=AUTH_HEADERS,
        json={"driver_id": driver_id, "truck_id": truck_id, "trailer_id": trailer_id},
    )
    assert assigned.status_code == 200, assigned.text
    for load_id in load_ids:
        accepted = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody",
            headers=AUTH_HEADERS,
            json={},
        )
        assert accepted.status_code == 200, accepted.text
    return trip_id


async def _start(client: AsyncClient, trip_id: int) -> None:
    started = await client.post(
        f"/api/v1/trips/{trip_id}/execution-signal",
        headers=AUTH_HEADERS,
        json={"source": "dispatcher_manual"},
    )
    assert started.status_code == 200, started.text


def _stop(load_body: dict, stop_type: str) -> dict:
    return next(row for row in load_body["stops"] if row["stop_type"] == stop_type)


async def _load(client: AsyncClient, load_id: int) -> dict:
    response = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


async def _audits(stop_id: int) -> list[dict]:
    return await _rows(
        """
        SELECT action, source, actor_user_id, actor_label, context_json
        FROM audit_events
        WHERE entity_type = 'load_stop' AND entity_id = :sid
        ORDER BY id
        """,
        {"sid": str(stop_id)},
    )


@contextmanager
def _fail_stop_arrived_audit():
    real_flush = AsyncSession.flush

    async def flush_wrapper(self, *args, **kwargs):
        for obj in list(self.new):
            if isinstance(obj, AuditEvent) and obj.action == "stop_arrived":
                raise RuntimeError("stop audit flush failure")
        return await real_flush(self, *args, **kwargs)

    with patch.object(AsyncSession, "flush", flush_wrapper):
        yield


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestStopExecution:
    async def test_arrival_then_departure_preserves_history(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        load_a, load_b = await integration_scope.create_ready_load_ids(2, tag_prefix="STOP-EXEC")
        status_a = (await _rows("SELECT status FROM loads WHERE id = :lid", {"lid": load_a}))[0]["status"]
        trip_id = await _prepare(client, integration_scope, [load_a, load_b])
        body_a = await _load(client, load_a)
        pickup = _stop(body_a, "PICKUP")
        drop = _stop(body_a, "DROP")
        body_b = await _load(client, load_b)
        other_pickup = _stop(body_b, "PICKUP")

        too_early = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{pickup['id']}/arrival",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert too_early.status_code == 409
        assert _code(too_early) == "INVALID_TRIP_STATUS_FOR_STOP_EXECUTION"

        await _start(client, trip_id)
        reserved = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{pickup['id']}/arrival",
            headers=AUTH_HEADERS,
            json={"source": "future_geofence"},
        )
        assert reserved.status_code == 422
        assert _code(reserved) == "EXECUTION_SIGNAL_SOURCE_RESERVED"

        before = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{pickup['id']}/departure",
            headers=AUTH_HEADERS,
            json={"source": "driver_app"},
        )
        assert before.status_code == 409
        assert _code(before) == "DEPARTURE_REQUIRES_ARRIVAL"

        first = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{pickup['id']}/arrival",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual", "occurred_at": "2026-10-16T12:00:00Z", "notes": "at door"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["replayed"] is False
        assert first.json()["load_status"] == status_a
        assert first.json()["trip_status"] == "in_progress"
        assert first.json()["membership_status_within_trip"] == "active"
        arrived = first.json()["arrived_at"]

        again = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{pickup['id']}/arrival",
            headers=AUTH_HEADERS,
            json={"source": "driver_app", "occurred_at": "2026-10-16T15:00:00Z"},
        )
        assert again.status_code == 200, again.text
        assert again.json()["replayed"] is True
        assert again.json()["arrived_at"] == arrived
        assert again.json()["departed_at"] is None

        left = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{pickup['id']}/departure",
            headers=AUTH_HEADERS,
            json={"source": "driver_app", "occurred_at": "2026-10-16T13:30:00Z"},
        )
        assert left.status_code == 200, left.text
        assert left.json()["replayed"] is False
        departed = left.json()["departed_at"]
        replay_depart = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{pickup['id']}/departure",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual", "occurred_at": "2026-10-16T18:00:00Z"},
        )
        assert replay_depart.status_code == 200, replay_depart.text
        assert replay_depart.json()["replayed"] is True
        assert replay_depart.json()["departed_at"] == departed
        assert replay_depart.json()["trip_status"] == "in_progress"

        audits = await _audits(int(pickup["id"]))
        assert [row["action"] for row in audits] == ["stop_arrived", "stop_departed"]
        assert {row["source"] for row in audits} == {"api"}
        assert audits[0]["context_json"]["signal_source"] == "dispatcher_manual"
        assert audits[1]["context_json"]["signal_source"] == "driver_app"
        assert all(row["actor_label"] or row["actor_user_id"] is not None for row in audits)

        other = await _rows(
            "SELECT arrived_at, departed_at FROM load_stops WHERE id = :sid",
            {"sid": other_pickup["id"]},
        )
        assert other[0]["arrived_at"] is None
        assert other[0]["departed_at"] is None
        membership_b = await _rows(
            "SELECT status_within_trip FROM trip_loads WHERE trip_id = :tid AND load_id = :lid",
            {"tid": trip_id, "lid": load_b},
        )
        assert membership_b[0]["status_within_trip"] == "active"
        assert (await _rows("SELECT custody_owner, status FROM loads WHERE id = :lid", {"lid": load_a}))[0][
            "custody_owner"
        ] == "trip"

        current = await _load(client, load_a)
        renamed = await client.patch(
            f"/api/v1/loads/{load_a}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": current["concurrency_version"],
                "stops": [
                    {
                        "id": pickup["id"],
                        "stop_type": "PICKUP",
                        "sequence": 0,
                        "facility_name": "Door 4",
                        "city": pickup.get("city"),
                        "state_or_province": pickup.get("state_or_province"),
                    },
                    {
                        "id": drop["id"],
                        "stop_type": "DROP",
                        "sequence": 1,
                        "city": drop.get("city"),
                        "state_or_province": drop.get("state_or_province"),
                    },
                ],
            },
        )
        assert renamed.status_code == 200, renamed.text
        kept = _stop(renamed.json(), "PICKUP")
        assert kept["id"] == pickup["id"]
        assert kept["facility_name"] == "Door 4"
        assert kept["arrived_at"] == arrived
        assert kept["departed_at"] == departed

        removed = await client.patch(
            f"/api/v1/loads/{load_a}",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": renamed.json()["concurrency_version"], "stops": []},
        )
        assert removed.status_code == 409
        assert _code(removed) == "LOAD_STOP_HISTORY_PROTECTED"

        await _exec("UPDATE load_stops SET stop_type = 'YARD' WHERE id = :sid", {"sid": other_pickup["id"]})
        invalid = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_b}/stops/{other_pickup['id']}/arrival",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert invalid.status_code == 409
        assert _code(invalid) == "INVALID_STOP_TYPE"
        assert (await _rows("SELECT arrived_at FROM load_stops WHERE id = :sid", {"sid": other_pickup["id"]}))[0][
            "arrived_at"
        ] is None

        delivered = await client.patch(
            f"/api/v1/loads/{load_a}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": renamed.json()["concurrency_version"],
                "stops": [
                    {
                        "id": pickup["id"],
                        "stop_type": "PICKUP",
                        "sequence": 0,
                        "facility_name": "Door 4",
                    },
                    {"id": drop["id"], "stop_type": "DELIVERY", "sequence": 1},
                ],
            },
        )
        assert delivered.status_code == 200, delivered.text
        delivery = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_a}/stops/{drop['id']}/arrival",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert delivery.status_code == 200, delivery.text
        assert delivery.json()["stop_type"] == "DELIVERY"
        assert delivery.json()["trip_status"] == "in_progress"
        assert (await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)).json()["status"] == "in_progress"

    async def test_required_audit_failure_rolls_back_arrival(
        self, client: AsyncClient, locked_prefix: str, integration_scope
    ):
        load_id = (await integration_scope.create_ready_load_ids(1, tag_prefix="STOP-AUDIT"))[0]
        trip_id = await _prepare(client, integration_scope, [load_id])
        await _start(client, trip_id)
        pickup = _stop(await _load(client, load_id), "PICKUP")
        with _fail_stop_arrived_audit():
            with pytest.raises(RuntimeError, match="stop audit flush failure"):
                await client.post(
                    f"/api/v1/trips/{trip_id}/loads/{load_id}/stops/{pickup['id']}/arrival",
                    headers=AUTH_HEADERS,
                    json={"source": "dispatcher_manual"},
                )
        assert (await _rows("SELECT arrived_at FROM load_stops WHERE id = :sid", {"sid": pickup["id"]}))[0][
            "arrived_at"
        ] is None
        assert await _audits(int(pickup["id"])) == []
