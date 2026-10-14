"""Issues I15/I16 — in_progress assignment lock and Decision 10 overlap."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.constants.trip_dispatch import (
    TRIP_ASSIGNMENT_LOCKED_IN_PROGRESS,
    TRIP_ASSIGNMENT_SCHEDULE_OVERLAP,
    TRIP_CONTAINER_STATUS_IN_PROGRESS,
)
from app.core.db_url import to_async_pg_url
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import AUTH_HEADERS, require_integration_tenant_database_url

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


async def _fleet_ids(client: AsyncClient) -> tuple[int, int, int] | None:
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


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
class TestTripAssignmentIssue15:
    async def test_in_progress_swap_rejected(self, client: AsyncClient, override_auth_tenant) -> None:
        assets = await _fleet_ids(client)
        if not assets:
            pytest.skip("fleet seed required")
        d0, t0, r0 = assets
        cr = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert cr.status_code == 201
        trip_id = cr.json()["id"]
        await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        sig = await client.post(f"/api/v1/trips/{trip_id}/execution-signal", headers=AUTH_HEADERS, json={})
        assert sig.status_code == 200
        assert sig.json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS

        dr = await client.get("/api/v1/drivers?limit=5", headers=AUTH_HEADERS)
        d_alt = int(dr.json()[1]["id"]) if len(dr.json()) > 1 else d0
        bad = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d_alt, "truck_id": t0, "trailer_id": r0},
        )
        assert bad.status_code == 409
        assert bad.json()["detail"]["code"] == TRIP_ASSIGNMENT_LOCKED_IN_PROGRESS

    async def test_in_progress_same_assignment_idempotent(self, client: AsyncClient, override_auth_tenant) -> None:
        assets = await _fleet_ids(client)
        if not assets:
            pytest.skip("fleet seed required")
        d0, t0, r0 = assets
        cr = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        trip_id = cr.json()["id"]
        await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        await client.post(f"/api/v1/trips/{trip_id}/execution-signal", headers=AUTH_HEADERS, json={})
        ok = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert ok.status_code == 200


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
class TestTripAssignmentIssue16:
    async def test_overlap_same_driver_blocked(self, client: AsyncClient, override_auth_tenant) -> None:
        assets = await _fleet_ids(client)
        if not assets:
            pytest.skip("fleet seed required")
        d0, t0, r0 = assets
        tenant_url = require_integration_tenant_database_url(context="i16_overlap")
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=4)

        cr_a = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        trip_a = cr_a.json()["id"]
        await client.put(
            f"/api/v1/trips/{trip_a}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        await client.post(f"/api/v1/trips/{trip_a}/execution-signal", headers=AUTH_HEADERS, json={})

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(to_async_pg_url(tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as db:
            await db.execute(
                text(
                    "update trips set expected_completion_at=:e where id=:i"
                ),
                {"e": end, "i": int(trip_a)},
            )
            await db.commit()
        await engine.dispose()

        cr_b = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        trip_b = cr_b.json()["id"]
        start = now + timedelta(hours=1)
        await client.put(
            f"/api/v1/trips/{trip_b}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": start.isoformat()},
        )
        bad = await client.put(
            f"/api/v1/trips/{trip_b}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert bad.status_code == 409
        assert bad.json()["detail"]["code"] == TRIP_ASSIGNMENT_SCHEDULE_OVERLAP

    async def test_missing_planned_start_does_not_overlap_block(
        self, client: AsyncClient, override_auth_tenant
    ) -> None:
        assets = await _fleet_ids(client)
        if not assets:
            pytest.skip("fleet seed required")
        d0, t0, r0 = assets
        cr = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        trip_id = cr.json()["id"]
        ok = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert ok.status_code == 200
