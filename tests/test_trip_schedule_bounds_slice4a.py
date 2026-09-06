"""COMMIT 4a: trip scheduling bounds — planned_start_at / expected_completion_at."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
AUTH_HEADERS = {"host": "pytest.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")

START_AT = "2026-09-01T14:00:00+00:00"
END_AT = "2026-09-03T18:00:00+00:00"


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
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> str:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200
    body = r0.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"P{uuid.uuid4().hex[:7].upper()}"
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


def _assert_iso_equal(actual: str | None, expected: str) -> None:
    assert actual is not None
    a = datetime.fromisoformat(actual.replace("Z", "+00:00"))
    e = datetime.fromisoformat(expected.replace("Z", "+00:00"))
    assert a == e


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestTripScheduleBoundsSlice4a:
    async def test_create_detail_list_null_schedule_fields(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201, r_create.text
        created = r_create.json()
        trip_id = int(created["id"])
        assert created["planned_start_at"] is None
        assert created["expected_completion_at"] is None
        assert created["status"] == TRIP_CONTAINER_STATUS_PLANNED

        r_get = await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)
        assert r_get.status_code == 200, r_get.text
        detail = r_get.json()
        assert detail["planned_start_at"] is None
        assert detail["expected_completion_at"] is None

        r_list = await client.get("/api/v1/trips?page=1&size=50", headers=AUTH_HEADERS)
        assert r_list.status_code == 200, r_list.text
        items = r_list.json().get("items") or []
        row = next((i for i in items if int(i["id"]) == trip_id), None)
        assert row is not None
        assert row["planned_start_at"] is None
        assert row["expected_completion_at"] is None

    async def test_put_schedule_set_and_clear(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201, r_create.text
        trip_id = int(r_create.json()["id"])
        status_before = r_create.json()["status"]

        r_set = await client.put(
            f"/api/v1/trips/{trip_id}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": START_AT, "expected_completion_at": END_AT},
        )
        assert r_set.status_code == 200, r_set.text
        body = r_set.json()
        _assert_iso_equal(body["planned_start_at"], START_AT)
        _assert_iso_equal(body["expected_completion_at"], END_AT)
        assert body["status"] == status_before

        r_get = await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)
        assert r_get.status_code == 200
        detail = r_get.json()
        _assert_iso_equal(detail["planned_start_at"], START_AT)
        _assert_iso_equal(detail["expected_completion_at"], END_AT)

        r_clear = await client.put(
            f"/api/v1/trips/{trip_id}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": None, "expected_completion_at": None},
        )
        assert r_clear.status_code == 200, r_clear.text
        cleared = r_clear.json()
        assert cleared["planned_start_at"] is None
        assert cleared["expected_completion_at"] is None
        assert cleared["status"] == status_before

    async def test_assignment_leaves_schedule_unchanged(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        assets = await _first_driver_truck_trailer(client)
        if not assets:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = assets

        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201
        trip_id = int(r_create.json()["id"])

        r_set = await client.put(
            f"/api/v1/trips/{trip_id}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": START_AT, "expected_completion_at": END_AT},
        )
        assert r_set.status_code == 200, r_set.text

        r_put = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_put.status_code == 200, r_put.text
        body = r_put.json()
        _assert_iso_equal(body["planned_start_at"], START_AT)
        _assert_iso_equal(body["expected_completion_at"], END_AT)

    async def test_schedule_fields_rejected_on_assignment_body(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        assets = await _first_driver_truck_trailer(client)
        if not assets:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = assets

        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201
        trip_id = int(r_create.json()["id"])

        r_put = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={
                "driver_id": d_id,
                "truck_id": t_id,
                "trailer_id": r_id,
                "planned_start_at": START_AT,
                "expected_completion_at": END_AT,
            },
        )
        assert r_put.status_code == 422

    async def test_cancelled_trip_schedule_update_rejected(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201
        trip_id = int(r_create.json()["id"])

        r_cancel = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=AUTH_HEADERS)
        assert r_cancel.status_code == 200

        r_put = await client.put(
            f"/api/v1/trips/{trip_id}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": START_AT, "expected_completion_at": END_AT},
        )
        assert r_put.status_code == 409
        payload = r_put.json()
        assert isinstance(payload.get("detail"), dict)
        assert payload["detail"].get("code") == "TRIP_CANCELLED"

    async def test_schedule_no_status_load_dispatch_side_effects(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        url = _tenant_async_url()
        if not url:
            pytest.skip("no tenant db url")

        lr = await client.get("/api/v1/loads?page=1&size=5", headers=AUTH_HEADERS)
        assert lr.status_code == 200
        items = lr.json().get("items") or []
        if not items:
            pytest.skip("no loads for tenant")
        load_id = int(items[0]["id"])
        load_status_before = str(items[0]["status"])

        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        tenant_id: int | None = None
        dispatch_before: int | None = None
        try:
            async with Session() as session:
                row = (
                    await session.execute(
                        text("SELECT tenant_id FROM loads WHERE id = :lid LIMIT 1"),
                        {"lid": load_id},
                    )
                ).first()
                if row is None:
                    pytest.skip("load row missing in db")
                tenant_id = int(row[0])
                dispatch_before = (
                    await session.execute(
                        text("SELECT count(*)::int FROM dispatch_trips WHERE tenant_id = :tid"),
                        {"tid": tenant_id},
                    )
                ).scalar()
        finally:
            await engine.dispose()

        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        if r_create.status_code != 201:
            pytest.skip("could not attach load: %s" % r_create.text)
        trip_id = int(r_create.json()["id"])
        status_before = r_create.json()["status"]

        r_set = await client.put(
            f"/api/v1/trips/{trip_id}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": START_AT, "expected_completion_at": END_AT},
        )
        assert r_set.status_code == 200, r_set.text
        assert r_set.json()["status"] == status_before

        engine2 = create_async_engine(url, pool_pre_ping=True)
        Session2 = async_sessionmaker(engine2, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session2() as session:
                dispatch_after = (
                    await session.execute(
                        text("SELECT count(*)::int FROM dispatch_trips WHERE tenant_id = :tid"),
                        {"tid": tenant_id},
                    )
                ).scalar()
                assert dispatch_after == dispatch_before

                st_after = (
                    await session.execute(
                        text("SELECT status FROM loads WHERE tenant_id = :tid AND id = :lid"),
                        {"tid": tenant_id, "lid": load_id},
                    )
                ).scalar()
                assert str(st_after) == load_status_before

                trip_status = (
                    await session.execute(
                        text("SELECT status FROM trips WHERE tenant_id = :tid AND id = :tid2"),
                        {"tid": tenant_id, "tid2": trip_id},
                    )
                ).scalar()
                assert str(trip_status) == status_before
        finally:
            await engine2.dispose()
