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
    trips_before = await client.get("/api/v1/trips", headers=AUTH_HEADERS)
    assert trips_before.status_code == 200


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
    loads = [tl for tl in trip.get("loads") or [] if tl.get("load_id") == load_id]
    assert loads
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
    assert "LOAD_FUTURE_MOVEMENT_RESERVED" in tr.text or "future movement" in tr.text.lower()
