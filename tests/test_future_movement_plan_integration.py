"""§9A Future Movement Plan — isolated tenant DB integration."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

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

REQUIRES_TENANT_DB = not (
    os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
)
AUTH_HEADERS = {"host": "pytest.truckerp.me"}


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
    async with integration_scope_context(client, AUTH_HEADERS, "fmp_integration") as scope:
        yield scope


def _member_load_ids(trip_body: dict) -> list[int]:
    return [int(x["load_id"]) for x in (trip_body.get("member_loads") or [])]


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
@pytest.mark.asyncio
async def test_save_unassigned_no_trip_row(client, integration_scope):
    load_id = await integration_scope.create_ready_load_id("FMP-U")
    r = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={
            "origin_kind": "follow_up_inbound",
            "lines": [{"load_id": load_id}],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "unassigned"
    assert body["converted_trip_id"] is None
    assert len(body.get("lines") or []) == 1


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
@pytest.mark.asyncio
async def test_convert_creates_numbered_trip_and_planned_membership(client, integration_scope):
    load_id = await integration_scope.create_ready_load_id("FMP-C")
    driver_id, _, _ = await integration_scope.create_fleet_bundle("FMP-C")
    cr = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={"lines": [{"load_id": load_id}]},
    )
    assert cr.status_code == 201, cr.text
    plan = cr.json()
    key = f"idem-{uuid.uuid4().hex}"
    cv = await client.post(
        f"/api/v1/future-movement-plans/{plan['id']}/convert",
        headers=AUTH_HEADERS,
        json={
            "driver_id": driver_id,
            "concurrency_version": plan["concurrency_version"],
            "conversion_idempotency_key": key,
        },
    )
    assert cv.status_code == 200, cv.text
    trip = cv.json()
    assert trip.get("trip_number")
    assert trip["status"] in ("planned", "assigned")
    assert load_id in _member_load_ids(trip)
    replay = await client.post(
        f"/api/v1/future-movement-plans/{plan['id']}/convert",
        headers=AUTH_HEADERS,
        json={
            "driver_id": driver_id,
            "concurrency_version": plan["concurrency_version"],
            "conversion_idempotency_key": key,
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == trip["id"]
    assert len(_member_load_ids(replay.json())) == len(_member_load_ids(trip))


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
@pytest.mark.asyncio
async def test_direct_post_trips_blocked_when_fmp_open(client, integration_scope):
    load_id = await integration_scope.create_ready_load_id("FMP-B")
    cr = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={"lines": [{"load_id": load_id}]},
    )
    assert cr.status_code == 201, cr.text
    tr = await client.post(
        "/api/v1/trips",
        headers=AUTH_HEADERS,
        json={"load_ids": [load_id]},
    )
    assert tr.status_code == 409, tr.text
    assert "LOAD_FUTURE_MOVEMENT_RESERVED" in tr.text


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
@pytest.mark.asyncio
async def test_foreign_fmp_blocks_convert(client, integration_scope):
    load_id = await integration_scope.create_ready_load_id("FMP-F")
    driver_id, _, _ = await integration_scope.create_fleet_bundle("FMP-F")
    p1 = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={"lines": [{"load_id": load_id}]},
    )
    assert p1.status_code == 201, p1.text
    p2 = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={"lines": [{"load_id": load_id}]},
    )
    assert p2.status_code == 409, p2.text
    plan = p1.json()
    cv = await client.post(
        f"/api/v1/future-movement-plans/{plan['id']}/convert",
        headers=AUTH_HEADERS,
        json={"driver_id": driver_id, "concurrency_version": plan["concurrency_version"]},
    )
    assert cv.status_code == 200, cv.text


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
@pytest.mark.asyncio
async def test_ltl_four_plus_six_two_plans_one_trip_each(client, integration_scope):
    ids = await integration_scope.create_ready_load_ids(10, tag_prefix="FMP-LTL")
    group_a, group_b = ids[:4], ids[4:]
    driver_a, _, _ = await integration_scope.create_fleet_bundle("FMP-LTL-A")
    driver_b, _, _ = await integration_scope.create_fleet_bundle("FMP-LTL-B")
    pa = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={"lines": [{"load_id": lid, "sequence_hint": i + 1} for i, lid in enumerate(group_a)]},
    )
    pb = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={"lines": [{"load_id": lid, "sequence_hint": i + 1} for i, lid in enumerate(group_b)]},
    )
    assert pa.status_code == 201 and pb.status_code == 201, f"{pa.text} {pb.text}"
    ta = await client.post(
        f"/api/v1/future-movement-plans/{pa.json()['id']}/convert",
        headers=AUTH_HEADERS,
        json={"driver_id": driver_a, "concurrency_version": pa.json()["concurrency_version"]},
    )
    tb = await client.post(
        f"/api/v1/future-movement-plans/{pb.json()['id']}/convert",
        headers=AUTH_HEADERS,
        json={"driver_id": driver_b, "concurrency_version": pb.json()["concurrency_version"]},
    )
    assert ta.status_code == 200 and tb.status_code == 200, f"{ta.text} {tb.text}"
    trip_a, trip_b = ta.json(), tb.json()
    assert trip_a["id"] != trip_b["id"]
    assert trip_a["trip_number"] != trip_b["trip_number"]
    assert set(_member_load_ids(trip_a)) == set(group_a)
    assert set(_member_load_ids(trip_b)) == set(group_b)


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
@pytest.mark.asyncio
async def test_update_and_cancel_load_plan_lines(client, integration_scope):
    l1 = await integration_scope.create_ready_load_id("FMP-UC1")
    l2 = await integration_scope.create_ready_load_id("FMP-UC2")
    cr = await client.post(
        "/api/v1/future-movement-plans",
        headers=AUTH_HEADERS,
        json={"lines": [{"load_id": l1}]},
    )
    assert cr.status_code == 201, cr.text
    plan = cr.json()
    up = await client.put(
        f"/api/v1/future-movement-plans/{plan['id']}",
        headers=AUTH_HEADERS,
        json={
            "concurrency_version": plan["concurrency_version"],
            "lines": [{"load_id": l1}, {"load_id": l2, "sequence_hint": 2}],
        },
    )
    assert up.status_code == 200, up.text
    assert len(up.json().get("lines") or []) == 2
    cancel = await client.post(
        f"/api/v1/future-movement-plans/{plan['id']}/cancel",
        headers=AUTH_HEADERS,
        json={"concurrency_version": up.json()["concurrency_version"]},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"
