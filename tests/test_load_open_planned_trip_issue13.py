"""Issue I13 — open planned trip fields on load GET."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
os.environ.setdefault("TEST_BYPASS_AUTH", "1")

from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import AUTH_HEADERS, require_integration_tenant_database_url
from tests.support.integration_ready_load import api_create_ready_load_ids

SKIP = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant():
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
@pytest.mark.asyncio
async def test_load_get_includes_open_planned_trip(client: AsyncClient, override_auth_tenant) -> None:
    require_integration_tenant_database_url(context="i13_open_planned")
    tag = f"I13-{uuid.uuid4().hex[:8]}"
    load_ids = await api_create_ready_load_ids(client, AUTH_HEADERS, 1, tag_prefix=tag)
    load_id = load_ids[0]
    tr = await client.post(
        "/api/v1/trips",
        headers=AUTH_HEADERS,
        json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
    )
    assert tr.status_code == 201
    trip_id = tr.json()["id"]
    trip_number = tr.json().get("trip_number")

    gr = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
    assert gr.status_code == 200
    body = gr.json()
    assert body.get("open_planned_trip_id") == trip_id
    assert body.get("open_planned_trip_number") == trip_number
    assert body.get("active_trip_id") in (None,)
