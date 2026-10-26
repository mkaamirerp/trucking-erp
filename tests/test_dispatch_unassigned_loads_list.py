"""Dispatch home: server-side unassigned load queue (Task 15)."""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
os.environ.setdefault("TEST_BYPASS_AUTH", "1")

from app.core.integration_db_guard import (
    IntegrationIsolationError,
    assert_tenant_database_url_allowed,
    database_name_from_url,
)
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
    install_integration_tenant_database_override,
)
from tests.support.integration_isolation import integration_auth_headers

AUTH_HEADERS = integration_auth_headers()
REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_DISPOSABLE_TENANT_DB = not (
    os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
)


def _disposable_integration_tenant_db_configured() -> bool:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw or not str(raw).strip():
        return False
    try:
        assert_tenant_database_url_allowed(str(raw).strip(), context="dispatch_unassigned_tests")
    except IntegrationIsolationError:
        return False
    return database_name_from_url(str(raw)) != "tenant_demo"


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
    if not _disposable_integration_tenant_db_configured():
        pytest.skip(
            "dispatch unassigned tests require TENANT_DATABASE_URL on a disposable integration DB "
            "(e.g. tenant_pytest or tenant_clone_*), never tenant_demo"
        )
    install_integration_tenant_database_override(app)
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_DISPOSABLE_TENANT_DB, reason="TENANT_DATABASE_URL required")
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
                        {
                            "stop_type": "PICKUP",
                            "sequence": 0,
                            "city": "A",
                            "state_or_province": "ON",
                            "appointment_date": date.today().isoformat(),
                        },
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
                    {
                        "stop_type": "PICKUP",
                        "sequence": 0,
                        "city": "A",
                        "state_or_province": "ON",
                        "appointment_date": date.today().isoformat(),
                    },
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

    async def _ready_load_with_pickup(
        self,
        client: AsyncClient,
        *,
        appointment_date: date | None,
        reference_suffix: str,
    ) -> int:
        cr = await client.post("/api/v1/loads", headers=AUTH_HEADERS, json={"status": "draft"})
        assert cr.status_code == 201, cr.text
        load_id = cr.json()["id"]
        cv = cr.json()["concurrency_version"]
        pickup: dict = {
            "stop_type": "PICKUP",
            "sequence": 0,
            "city": "Queue",
            "state_or_province": "TX",
        }
        if appointment_date is not None:
            pickup["appointment_date"] = appointment_date.isoformat()
            pickup["appointment_time_text"] = "10:00"
        patch = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": cv,
                "broker_name_snapshot": "T",
                "broker_load_reference": f"BR-{reference_suffix}-{uuid.uuid4().hex[:6]}",
                "stops": [
                    pickup,
                    {"stop_type": "DELIVERY", "sequence": 1, "city": "Dest", "state_or_province": "TX"},
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

    async def test_dispatch_unassigned_pagination_and_pickup_priority(
        self, client: AsyncClient, override_auth_tenant
    ) -> None:
        """101+ eligible loads: paginate past 50; due-today load sorts ahead of far-future bulk."""
        today = date.today()
        overdue_id = await self._ready_load_with_pickup(
            client, appointment_date=today - timedelta(days=2), reference_suffix="overdue"
        )
        today_id = await self._ready_load_with_pickup(
            client, appointment_date=today, reference_suffix="due-today"
        )
        future_far = today + timedelta(days=90)
        for i in range(100):
            await self._ready_load_with_pickup(
                client, appointment_date=future_far, reference_suffix=f"bulk{i}"
            )

        page1 = await client.get(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            params={"dispatch_unassigned": "true", "page": 1, "size": 50},
        )
        assert page1.status_code == 200, page1.text
        body1 = page1.json()
        assert body1["total"] >= 102
        assert body1["page"] == 1
        assert body1["size"] == 50
        assert len(body1["items"]) == 50
        ids_p1 = [x["id"] for x in body1["items"]]
        assert overdue_id in ids_p1
        assert today_id in ids_p1
        assert ids_p1.index(overdue_id) < ids_p1.index(today_id)

        page2 = await client.get(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            params={"dispatch_unassigned": "true", "page": 2, "size": 50},
        )
        assert page2.status_code == 200
        assert len(page2.json()["items"]) == 50

        page3 = await client.get(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            params={"dispatch_unassigned": "true", "page": 3, "size": 50},
        )
        assert page3.status_code == 200
        assert len(page3.json()["items"]) >= 2
