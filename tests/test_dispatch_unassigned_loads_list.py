"""Dispatch home: server-side unassigned load queue (Task 15)."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
os.environ.setdefault("TEST_BYPASS_AUTH", "1")

from app.main import app
from tests.support.demo_clone_integration import install_demo_clone_tenant_db_override
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

AUTH_HEADERS = {"host": "pytest.truckerp.me"}
REQUIRES_DB = not os.environ.get("DATABASE_URL")


@pytest.fixture
def override_auth_tenant():
    install_host_aligned_current_user_and_tenant(app)
    install_demo_clone_tenant_db_override(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestDispatchUnassignedLoadsList:
    async def test_dispatch_unassigned_returns_ready_load(self, client: AsyncClient, override_auth_tenant) -> None:
        cr = await client.post("/api/v1/loads", headers=AUTH_HEADERS, json={"status": "draft"})
        assert cr.status_code == 201, cr.text
        load_id = cr.json()["id"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": cr.json()["concurrency_version"],
            },
        )
        if mr.status_code != 200:
            patch = await client.patch(
                f"/api/v1/loads/{load_id}",
                headers=AUTH_HEADERS,
                json={
                    "expected_concurrency_version": cr.json()["concurrency_version"],
                    "broker_name_snapshot": "T",
                    "broker_load_reference": f"BR-{uuid.uuid4().hex[:6]}",
                    "stops": [
                        {"stop_type": "PICKUP", "sequence": 0, "city": "A", "state_or_province": "ON"},
                        {"stop_type": "DELIVERY", "sequence": 1, "city": "B", "state_or_province": "ON"},
                    ],
                },
            )
            assert patch.status_code == 200, patch.text
            cv = patch.json()["concurrency_version"]
            mr = await client.post(
                f"/api/v1/loads/{load_id}/mark-ready",
                headers=AUTH_HEADERS,
                json={"expected_concurrency_version": cv},
            )
        assert mr.status_code == 200, mr.text

        listed = await client.get(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            params={"dispatch_unassigned": "true", "page": 1, "size": 50},
        )
        assert listed.status_code == 200, listed.text
        ids = [x["id"] for x in listed.json().get("items", [])]
        assert load_id in ids

    async def _ready_load(self, client: AsyncClient) -> int:
        cr = await client.post("/api/v1/loads", headers=AUTH_HEADERS, json={"status": "draft"})
        assert cr.status_code == 201, cr.text
        load_id = cr.json()["id"]
        cv = cr.json()["concurrency_version"]
        patch = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": cv,
                "broker_name_snapshot": "T",
                "broker_load_reference": f"BR-{uuid.uuid4().hex[:6]}",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "city": "A", "state_or_province": "ON"},
                    {"stop_type": "DELIVERY", "sequence": 1, "city": "B", "state_or_province": "ON"},
                ],
            },
        )
        assert patch.status_code == 200, patch.text
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": patch.json()["concurrency_version"]},
        )
        assert mr.status_code == 200, mr.text
        return load_id

    async def test_planned_trip_member_not_listed_as_unassigned(
        self, client: AsyncClient, override_auth_tenant
    ) -> None:
        load_id = await self._ready_load(client)
        trip = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "load_ids": [load_id]},
        )
        assert trip.status_code in (200, 201), trip.text

        listed = await client.get(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            params={"dispatch_unassigned": "true", "page": 1, "size": 50},
        )
        assert listed.status_code == 200
        ids = [x["id"] for x in listed.json().get("items", [])]
        assert load_id not in ids
