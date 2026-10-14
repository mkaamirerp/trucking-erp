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
os.environ.setdefault("TEST_BYPASS_AUTH", "1")

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
from tests.support.integration_test_resources import integration_scope_context

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


@pytest.fixture
async def integration_scope(client, override_auth_tenant):
    async with integration_scope_context(client, AUTH_HEADERS, "i15_i16_assignment") as scope:
        yield scope


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
class TestTripAssignmentIssue15:
    async def test_in_progress_swap_rejected(self, integration_scope) -> None:
        d0, t0, r0 = await integration_scope.create_fleet_bundle(f"I15-{uuid.uuid4().hex[:6]}")
        d1, _, _ = await integration_scope.create_fleet_bundle(f"I15B-{uuid.uuid4().hex[:6]}")
        tr = await integration_scope.post_planned_trip([])
        assert tr.status_code == 201
        trip_id = tr.json()["id"]
        await integration_scope.client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        sig = await integration_scope.client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert sig.status_code == 200
        assert sig.json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS

        bad = await integration_scope.client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d1, "truck_id": t0, "trailer_id": r0},
        )
        assert bad.status_code == 409
        assert bad.json()["detail"]["code"] == TRIP_ASSIGNMENT_LOCKED_IN_PROGRESS

    async def test_in_progress_same_assignment_idempotent(self, integration_scope) -> None:
        d0, t0, r0 = await integration_scope.create_fleet_bundle(f"I15I-{uuid.uuid4().hex[:6]}")
        tr = await integration_scope.post_planned_trip([])
        trip_id = tr.json()["id"]
        await integration_scope.client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        await integration_scope.client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        ok = await integration_scope.client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert ok.status_code == 200


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
class TestTripAssignmentIssue16:
    async def test_overlap_same_driver_blocked(self, integration_scope) -> None:
        d0, t0, r0 = await integration_scope.create_fleet_bundle(f"I16-{uuid.uuid4().hex[:6]}")
        tenant_url = integration_scope.tenant_url
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=4)

        tr_a = await integration_scope.post_planned_trip([])
        trip_a = tr_a.json()["id"]
        asg_a = await integration_scope.client.put(
            f"/api/v1/trips/{trip_a}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert asg_a.status_code == 200
        sch_a = await integration_scope.client.put(
            f"/api/v1/trips/{trip_a}/schedule",
            headers=AUTH_HEADERS,
            json={
                "planned_start_at": now.isoformat(),
                "expected_completion_at": end.isoformat(),
            },
        )
        assert sch_a.status_code == 200
        sig_a = await integration_scope.client.post(
            f"/api/v1/trips/{trip_a}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert sig_a.status_code == 200
        assert sig_a.json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS

        tr_b = await integration_scope.post_planned_trip([])
        trip_b = tr_b.json()["id"]
        start = now + timedelta(hours=1)
        sched = await integration_scope.client.put(
            f"/api/v1/trips/{trip_b}/schedule",
            headers=AUTH_HEADERS,
            json={
                "planned_start_at": start.isoformat(),
                "expected_completion_at": None,
            },
        )
        assert sched.status_code == 200

        bad = await integration_scope.client.put(
            f"/api/v1/trips/{trip_b}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert bad.status_code == 409
        assert bad.json()["detail"]["code"] == TRIP_ASSIGNMENT_SCHEDULE_OVERLAP

    async def test_missing_planned_start_does_not_overlap_block(self, integration_scope) -> None:
        d0, t0, r0 = await integration_scope.create_fleet_bundle(f"I16M-{uuid.uuid4().hex[:6]}")
        tr = await integration_scope.post_planned_trip([])
        trip_id = tr.json()["id"]
        ok = await integration_scope.client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        assert ok.status_code == 200

    async def test_non_overlapping_driver_allowed(self, integration_scope) -> None:
        d0, t0, r0 = await integration_scope.create_fleet_bundle(f"I16N-{uuid.uuid4().hex[:6]}")
        d1, t1, r1 = await integration_scope.create_fleet_bundle(f"I16N2-{uuid.uuid4().hex[:6]}")
        tenant_url = integration_scope.tenant_url
        now = datetime.now(timezone.utc)

        tr_a = await integration_scope.post_planned_trip([])
        trip_a = tr_a.json()["id"]
        await integration_scope.client.put(
            f"/api/v1/trips/{trip_a}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d0, "truck_id": t0, "trailer_id": r0},
        )
        await integration_scope.client.put(
            f"/api/v1/trips/{trip_a}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": now.isoformat()},
        )

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(to_async_pg_url(tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as db:
            await db.execute(
                text("update trips set expected_completion_at=:e where id=:i"),
                {"e": now + timedelta(hours=2), "i": int(trip_a)},
            )
            await db.commit()
        await engine.dispose()

        tr_b = await integration_scope.post_planned_trip([])
        trip_b = tr_b.json()["id"]
        later = now + timedelta(hours=5)
        await integration_scope.client.put(
            f"/api/v1/trips/{trip_b}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": later.isoformat()},
        )
        ok = await integration_scope.client.put(
            f"/api/v1/trips/{trip_b}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d1, "truck_id": t1, "trailer_id": r1},
        )
        assert ok.status_code == 200
