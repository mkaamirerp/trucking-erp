"""Decision 7 slice: POST /trips/{id}/execution-signal — integration tests."""

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
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "demo.truckerp.me"}
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
    yield
    clear_current_user_and_tenant_overrides(app)


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


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestTripExecutionSignalSlice7Http:
    async def test_happy_path_assigned_to_in_progress(self, client: AsyncClient, override_auth_tenant):
        assets = await _first_driver_truck_trailer(client)
        if not assets:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = assets

        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201, r_create.text
        trip_id = int(r_create.json()["id"])

        r_put = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_put.status_code == 200, r_put.text
        assert r_put.json()["status"] == "assigned"

        r_start = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual", "reason_note": "Start trip", "signal_at": None},
        )
        assert r_start.status_code == 200, r_start.text
        assert r_start.json()["status"] == "in_progress"

    async def test_planned_trip_rejected_with_trip_not_assigned(self, client: AsyncClient, override_auth_tenant):
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201
        trip_id = int(r_create.json()["id"])

        r_start = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert r_start.status_code == 409
        payload = r_start.json()
        assert isinstance(payload.get("detail"), dict)
        assert payload["detail"].get("code") == "TRIP_NOT_ASSIGNED"

    async def test_cancelled_trip_rejected_with_trip_cancelled(self, client: AsyncClient, override_auth_tenant):
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201
        trip_id = int(r_create.json()["id"])

        r_cancel = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=AUTH_HEADERS)
        assert r_cancel.status_code == 200

        r_start = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert r_start.status_code == 409
        payload = r_start.json()
        assert isinstance(payload.get("detail"), dict)
        assert payload["detail"].get("code") == "TRIP_CANCELLED"

    async def test_completed_trip_rejected_with_trip_already_completed(self, client: AsyncClient, override_auth_tenant):
        url = _tenant_async_url()
        if not url:
            pytest.skip("no tenant db url")
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
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_put.status_code == 200

        # Force-complete via tenant DB for this test (no completed endpoint in this slice).
        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                row = (
                    await session.execute(
                        text("SELECT tenant_id FROM trips WHERE id = :id LIMIT 1"),
                        {"id": trip_id},
                    )
                ).first()
                if row is None:
                    pytest.skip("trip row missing in db")
                await session.execute(
                    text("UPDATE trips SET status = 'completed' WHERE id = :id"),
                    {"id": trip_id},
                )
                await session.commit()
        finally:
            await engine.dispose()

        r_start = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert r_start.status_code == 409
        payload = r_start.json()
        assert isinstance(payload.get("detail"), dict)
        assert payload["detail"].get("code") == "TRIP_ALREADY_COMPLETED"

    async def test_already_in_progress_is_idempotent_and_no_duplicate_audit(
        self, client: AsyncClient, override_auth_tenant
    ):
        url = _tenant_async_url()
        if not url:
            pytest.skip("no tenant db url")
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
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_put.status_code == 200

        # Count audit events before starting.
        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        tenant_id: int | None = None
        before_cnt: int = 0
        try:
            async with Session() as session:
                row = (
                    await session.execute(
                        text("SELECT tenant_id FROM trips WHERE id = :id LIMIT 1"),
                        {"id": trip_id},
                    )
                ).first()
                if row is None:
                    pytest.skip("trip row missing")
                tenant_id = int(row[0])
                try:
                    before_cnt = (
                        await session.execute(
                            text(
                                "SELECT count(*)::int FROM audit_events WHERE tenant_id = :tid "
                                "AND entity_type = 'trip' AND action = 'trip_execution_started'"
                            ),
                            {"tid": tenant_id},
                        )
                    ).scalar() or 0
                except Exception:
                    pytest.skip("audit_events table missing or unreadable")
        finally:
            await engine.dispose()

        r_start1 = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "driver_app", "reason_note": None, "signal_at": None},
        )
        assert r_start1.status_code == 200, r_start1.text
        assert r_start1.json()["status"] == "in_progress"

        r_start2 = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "driver_app", "reason_note": "duplicate", "signal_at": None},
        )
        assert r_start2.status_code == 200, r_start2.text
        assert r_start2.json()["status"] == "in_progress"

        engine2 = create_async_engine(url, pool_pre_ping=True)
        Session2 = async_sessionmaker(engine2, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session2() as session:
                after_cnt = (
                    await session.execute(
                        text(
                            "SELECT count(*)::int FROM audit_events WHERE tenant_id = :tid "
                            "AND entity_type = 'trip' AND action = 'trip_execution_started'"
                        ),
                        {"tid": tenant_id},
                    )
                ).scalar() or 0
                assert after_cnt == before_cnt + 1
        finally:
            await engine2.dispose()

    async def test_no_load_status_change_no_dispatch_trips_change_and_audit_once(self, client: AsyncClient, override_auth_tenant):
        url = _tenant_async_url()
        if not url:
            pytest.skip("no tenant db url")
        assets = await _first_driver_truck_trailer(client)
        if not assets:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = assets

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
        audit_before: int | None = None
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
                try:
                    audit_before = (
                        await session.execute(
                            text(
                                "SELECT count(*)::int FROM audit_events WHERE tenant_id = :tid "
                                "AND entity_type = 'trip' AND action = 'trip_execution_started'"
                            ),
                            {"tid": tenant_id},
                        )
                    ).scalar() or 0
                except Exception:
                    pytest.skip("audit_events table missing or unreadable")
        finally:
            await engine.dispose()

        # Create trip with load attached
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        if r_create.status_code != 201:
            pytest.skip("could not attach load: %s" % r_create.text)
        trip_id = int(r_create.json()["id"])

        r_put = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_put.status_code == 200, r_put.text

        r_start = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual", "reason_note": "start", "signal_at": None},
        )
        assert r_start.status_code == 200, r_start.text
        assert r_start.json()["status"] == "in_progress"

        # Second call should be idempotent; audit should not increment.
        r_start2 = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual", "reason_note": "dup", "signal_at": None},
        )
        assert r_start2.status_code == 200, r_start2.text

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

                audit_after = (
                    await session.execute(
                        text(
                            "SELECT count(*)::int FROM audit_events WHERE tenant_id = :tid "
                            "AND entity_type = 'trip' AND action = 'trip_execution_started'"
                        ),
                        {"tid": tenant_id},
                    )
                ).scalar() or 0
                assert audit_after == audit_before + 1
        finally:
            await engine2.dispose()

        lr2 = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        assert lr2.status_code == 200
        assert lr2.json().get("status") == load_status_before

    async def test_future_geofence_rejected_with_clear_message(self, client: AsyncClient, override_auth_tenant):
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
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_put.status_code == 200

        r_start = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "future_geofence"},
        )
        assert r_start.status_code in (400, 422)
        body = r_start.json()
        if isinstance(body.get("detail"), dict):
            assert "reserved" in str(body["detail"].get("detail") or "").lower()

