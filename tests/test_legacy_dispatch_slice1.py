"""Legacy dispatch cutover Slice 1: PATCH cannot create new dispatched; DB stays clean; planned trips still mint."""

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

from app.constants.trip_dispatch import LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
from app.core.db_url import to_async_pg_url
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "demo.truckerp.me"}


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


def _cv(data: dict) -> int:
    return int(data["concurrency_version"])


def _detail_code(payload: dict) -> str | None:
    d = payload.get("detail")
    if isinstance(d, dict):
        return d.get("code")
    return None


@pytest.fixture(autouse=True)
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestSlice1RejectedPatchLeavesNoFreightRows:
    async def _first_driver_truck(self, client) -> tuple[int, int] | None:
        dr = await client.get("/api/v1/drivers?limit=5", headers=AUTH_HEADERS)
        tr = await client.get("/api/v1/trucks?page=1&size=5", headers=AUTH_HEADERS)
        if dr.status_code != 200 or tr.status_code != 200:
            return None
        dlist = dr.json()
        titems = tr.json().get("items") or []
        if not dlist or not titems:
            return None
        return int(dlist[0]["id"]), int(titems[0]["id"])

    @pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
    async def test_rejected_dispatched_transition_does_not_create_rows(
        self, client, override_auth_tenant
    ) -> None:
        ids = await self._first_driver_truck(client)
        if ids is None:
            pytest.skip("No driver/truck in tenant DB")
        driver_id, truck_id = ids

        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"SL1-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]

        url = _tenant_async_url()
        assert url
        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:

            async def _counts(session: AsyncSession) -> tuple[int, int, int]:
                dt = (
                    await session.execute(
                        text("SELECT count(*)::int FROM dispatch_trips WHERE load_id = :lid"),
                        {"lid": load_id},
                    )
                ).scalar()
                trp = (
                    await session.execute(
                        text(
                            """
                            SELECT count(*)::int FROM trips t
                            INNER JOIN dispatch_trips d ON d.id = t.legacy_dispatch_trip_id
                            WHERE d.load_id = :lid
                            """
                        ),
                        {"lid": load_id},
                    )
                ).scalar()
                tl = (
                    await session.execute(
                        text("SELECT count(*)::int FROM trip_loads WHERE load_id = :lid"),
                        {"lid": load_id},
                    )
                ).scalar()
                return int(dt or 0), int(trp or 0), int(tl or 0)

            async with Session() as session:
                c0 = await _counts(session)

            bad = await client.patch(
                f"/api/v1/loads/{load_id}",
                headers=AUTH_HEADERS,
                json={
                    "driver_id": driver_id,
                    "truck_id": truck_id,
                    "status": "dispatched",
                    "expected_concurrency_version": _cv(cr.json()),
                },
            )
            assert bad.status_code == 409
            assert _detail_code(bad.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED

            async with Session() as session:
                c1 = await _counts(session)

            assert c0 == c1 == (0, 0, 0)

            row = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
            assert row.status_code == 200
            j = row.json()
            assert j.get("active_dispatch_trip_id") in (None,)
            assert j.get("active_trip_id") in (None,)
            assert j.get("trip_number") in (None, "")
        finally:
            await engine.dispose()


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestSlice1PlannedTripStillMints:
    async def test_post_planned_trip_returns_trip_number(self, client, override_auth_tenant) -> None:
        r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
        assert r0.status_code == 200
        if not r0.json().get("prefix_locked"):
            p1 = f"S{uuid.uuid4().hex[:7].upper()}"
            lock = await client.put(
                "/api/v1/admin/dispatch-numbering",
                headers=AUTH_HEADERS,
                json={"trip_number_prefix": p1},
            )
            assert lock.status_code == 200, lock.text

        trip = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={},
        )
        assert trip.status_code == 201, trip.text
        tn = trip.json().get("trip_number")
        assert tn and len(tn) >= 3
