"""POST /trips creates planned Trips only — status guard."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.trip_dispatch import TRIP_CONTAINER_STATUS_PLANNED
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "demo.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")


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
async def locked_prefix(client, override_auth_tenant) -> str:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200
    body = r0.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"G{uuid.uuid4().hex[:7].upper()}"
    r1 = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": prefix},
    )
    assert r1.status_code == 200, r1.text
    return prefix


async def _first_driver_truck_trailer(client: AsyncClient) -> tuple[int, int, int] | None:
    dr = await client.get("/api/v1/drivers?limit=5", headers=AUTH_HEADERS)
    tr = await client.get("/api/v1/trucks?page=1&size=5", headers=AUTH_HEADERS)
    rr = await client.get("/api/v1/trailers?page=1&size=5", headers=AUTH_HEADERS)
    if dr.status_code != 200 or tr.status_code != 200 or rr.status_code != 200:
        return None
    dlist = dr.json()
    tlist = tr.json().get("items") or []
    rlist = rr.json().get("items") or []
    if not dlist or not tlist or not rlist:
        return None
    return int(dlist[0]["id"]), int(tlist[0]["id"]), int(rlist[0]["id"])


def _assert_invalid_create_status(r) -> None:
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_TRIP_STATUS"
    assert detail["detail"] == "Trip create only allows status 'planned' (or omit)"


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestTripCreateStatusGuard:
    async def test_omit_status_planned(self, client: AsyncClient, locked_prefix: str, override_auth_tenant):
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"job_type": "freight_load", "load_ids": []},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == TRIP_CONTAINER_STATUS_PLANNED
        assert body.get("assigned_at") is None

    async def test_null_status_planned(self, client: AsyncClient, locked_prefix: str, override_auth_tenant):
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": None, "job_type": "freight_load", "load_ids": []},
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == TRIP_CONTAINER_STATUS_PLANNED
        assert r.json().get("assigned_at") is None

    async def test_blank_status_planned(self, client: AsyncClient, locked_prefix: str, override_auth_tenant):
        for blank in ("", "   "):
            r = await client.post(
                "/api/v1/trips",
                headers=AUTH_HEADERS,
                json={"status": blank, "job_type": "freight_load", "load_ids": []},
            )
            assert r.status_code == 201, r.text
            assert r.json()["status"] == TRIP_CONTAINER_STATUS_PLANNED
            assert r.json().get("assigned_at") is None

    async def test_explicit_planned(self, client: AsyncClient, locked_prefix: str, override_auth_tenant):
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == TRIP_CONTAINER_STATUS_PLANNED
        assert r.json().get("assigned_at") is None

    @pytest.mark.parametrize(
        "bad_status",
        ["assigned", "in_progress", "completed", "cancelled", "active", "custom_xyz"],
    )
    async def test_reject_non_planned_status(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant, bad_status: str
    ):
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": bad_status, "job_type": "freight_load", "load_ids": []},
        )
        _assert_invalid_create_status(r)

    async def test_planned_with_resource_prefill_stays_planned(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        ids = await _first_driver_truck_trailer(client)
        if ids is None:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = ids
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={
                "status": "planned",
                "job_type": "freight_load",
                "load_ids": [],
                "driver_id": d_id,
                "truck_id": t_id,
                "trailer_id": r_id,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == TRIP_CONTAINER_STATUS_PLANNED
        assert body["driver_id"] == d_id
        assert body["truck_id"] == t_id
        assert body["trailer_id"] == r_id
        assert body.get("assigned_at") is None

    async def test_put_assignment_still_promotes_planned_to_assigned(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        ids = await _first_driver_truck_trailer(client)
        if ids is None:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = ids
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201, r_create.text
        trip_id = int(r_create.json()["id"])
        assert r_create.json()["status"] == TRIP_CONTAINER_STATUS_PLANNED

        r_put = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_put.status_code == 200, r_put.text
        body = r_put.json()
        assert body["status"] == "assigned"
        assert body.get("assigned_at") is not None
