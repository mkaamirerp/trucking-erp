"""Phase 3A: GET /api/v1/trips/{id} — read-only; membership from trip_loads, not active_trip_id."""
from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.main import app
from app.models.load import Load
from app.models.trip import Trip, TripLoad
from app.services.trips import get_trip_detail, list_trips
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
REQUIRES_DB = not os.environ.get("DATABASE_URL")
# conftest sets a placeholder so Settings() works; that URL must not be used for ASGI tenant middleware.
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
async def tenant_session():
    from app.core.db_url import to_async_pg_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        pytest.skip("TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL required")
    url = to_async_pg_url(raw)
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            yield session
    finally:
        await engine.dispose()


AUTH_HEADERS = {"host": "pytest.truckerp.me"}


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB required")
class TestGetTripDetailService:
    async def test_membership_from_trip_loads_not_active_trip_id(
        self, tenant_session: AsyncSession
    ) -> None:
        tid = (
            await tenant_session.execute(
                text("SELECT tenant_id FROM trips WHERE tenant_id IS NOT NULL LIMIT 1")
            )
        ).scalar()
        if tid is None:
            tid = (
                await tenant_session.execute(
                    text("SELECT tenant_id FROM loads WHERE tenant_id IS NOT NULL LIMIT 1")
                )
            ).scalar()
        if tid is None:
            pytest.skip("no tenant_id row")
        tid = int(tid)
        u = uuid.uuid4().hex[:8]
        other = Trip(
            tenant_id=tid,
            trip_number=f"ZZ-OTHER-{u}",
            status="open",
            job_type="freight",
        )
        tenant_session.add(other)
        await tenant_session.flush()

        load1 = Load(
            tenant_id=tid,
            load_number=f"MEM-{u}-1",
            concurrency_version=1,
            status="draft",
            active_trip_id=other.id,
        )
        load2 = Load(
            tenant_id=tid,
            load_number=f"MEM-{u}-2",
            concurrency_version=1,
            status="draft",
            active_trip_id=None,
        )
        tenant_session.add(load1)
        tenant_session.add(load2)
        await tenant_session.flush()

        main_trip = Trip(
            tenant_id=tid,
            trip_number=f"MAIN-{u}",
            status="open",
            job_type="freight",
        )
        tenant_session.add(main_trip)
        await tenant_session.flush()

        tenant_session.add(
            TripLoad(
                tenant_id=tid,
                trip_id=main_trip.id,
                load_id=load1.id,
                status_within_trip="active",
            )
        )
        tenant_session.add(
            TripLoad(
                tenant_id=tid,
                trip_id=main_trip.id,
                load_id=load2.id,
                status_within_trip="active",
            )
        )
        await tenant_session.commit()

        detail = await get_trip_detail(tenant_session, tid, int(main_trip.id))
        assert detail is not None
        assert len(detail.member_loads) == 2
        lids = {m.load_id for m in detail.member_loads}
        assert load1.id in lids
        assert load2.id in lids
        assert any(m.load_id == load1.id and m.load_number == f"MEM-{u}-1" for m in detail.member_loads)
        # load1.active_trip_id points elsewhere, but it still listed via trip_loads
        assert load1.active_trip_id == other.id

    async def test_trip_not_found(self, tenant_session: AsyncSession) -> None:
        tid = (
            await tenant_session.execute(text("SELECT tenant_id FROM trips LIMIT 1"))
        ).scalar()
        if tid is None:
            pytest.skip("no trips row")
        tid = int(tid)
        out = await get_trip_detail(tenant_session, tid, 9_999_999_999)
        assert out is None


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB required")
class TestListTripsService:
    async def test_member_load_count_from_trip_loads(self, tenant_session: AsyncSession) -> None:
        tid = (
            await tenant_session.execute(
                text("SELECT tenant_id FROM trips WHERE tenant_id IS NOT NULL LIMIT 1")
            )
        ).scalar()
        if tid is None:
            tid = (
                await tenant_session.execute(
                    text("SELECT tenant_id FROM loads WHERE tenant_id IS NOT NULL LIMIT 1")
                )
            ).scalar()
        if tid is None:
            pytest.skip("no tenant_id row")
        tid = int(tid)
        u = uuid.uuid4().hex[:8]
        load1 = Load(
            tenant_id=tid,
            load_number=f"LST-{u}-1",
            concurrency_version=1,
            status="draft",
        )
        load2 = Load(
            tenant_id=tid,
            load_number=f"LST-{u}-2",
            concurrency_version=1,
            status="draft",
        )
        tenant_session.add(load1)
        tenant_session.add(load2)
        await tenant_session.flush()
        trip = Trip(
            tenant_id=tid,
            trip_number=f"LST-TRIP-{u}",
            status="open",
            job_type="freight",
        )
        tenant_session.add(trip)
        await tenant_session.flush()
        tenant_session.add(
            TripLoad(
                tenant_id=tid,
                trip_id=trip.id,
                load_id=load1.id,
                status_within_trip="active",
            )
        )
        tenant_session.add(
            TripLoad(
                tenant_id=tid,
                trip_id=trip.id,
                load_id=load2.id,
                status_within_trip="active",
            )
        )
        await tenant_session.commit()

        page = await list_trips(tenant_session, tid, page=1, size=100)
        row = next((x for x in page["items"] if x.id == trip.id), None)
        assert row is not None
        assert row.member_load_count == 2
        assert row.first_member is not None
        assert row.first_member.load_number in (f"LST-{u}-1", f"LST-{u}-2")

    async def test_list_tenant_isolation(self, tenant_session: AsyncSession) -> None:
        tid = (
            await tenant_session.execute(text("SELECT tenant_id FROM trips LIMIT 1"))
        ).scalar()
        if tid is None:
            pytest.skip("no trips row")
        tid = int(tid)
        u = uuid.uuid4().hex[:8]
        trip = Trip(
            tenant_id=tid,
            trip_number=f"ISO-ONLY-{u}",
            status="open",
            job_type="freight",
        )
        tenant_session.add(trip)
        await tenant_session.commit()

        wrong_tenant = tid + 9_000_000
        page = await list_trips(tenant_session, wrong_tenant, page=1, size=200)
        ids = [x.id for x in page["items"]]
        assert trip.id not in ids

    async def test_search_finds_trip_by_member_load_number(self, tenant_session: AsyncSession) -> None:
        tid = (
            await tenant_session.execute(
                text("SELECT tenant_id FROM trips WHERE tenant_id IS NOT NULL LIMIT 1")
            )
        ).scalar()
        if tid is None:
            tid = (
                await tenant_session.execute(text("SELECT tenant_id FROM loads LIMIT 1"))
            ).scalar()
        if tid is None:
            pytest.skip("no tenant_id row")
        tid = int(tid)
        u = uuid.uuid4().hex[:10]
        unique_ln = f"SRCH-REF-{u}"
        load1 = Load(
            tenant_id=tid,
            load_number=unique_ln,
            concurrency_version=1,
            status="draft",
        )
        tenant_session.add(load1)
        await tenant_session.flush()
        trip = Trip(
            tenant_id=tid,
            trip_number=f"SRCH-TR-{u}",
            status="open",
            job_type="freight",
        )
        tenant_session.add(trip)
        await tenant_session.flush()
        tenant_session.add(
            TripLoad(
                tenant_id=tid,
                trip_id=trip.id,
                load_id=load1.id,
                status_within_trip="active",
            )
        )
        await tenant_session.commit()

        page = await list_trips(tenant_session, tid, search=unique_ln[:16], page=1, size=50)
        ids = [x.id for x in page["items"]]
        assert trip.id in ids


@pytest.mark.skipif(REQUIRES_DB or _PLACEHOLDER_PLATFORM_DB, reason="Real DATABASE_URL required (not conftest placeholder)")
class TestGetTripHttp:
    @pytest.mark.asyncio
    async def test_404_for_missing_trip(self, client, override_auth_tenant) -> None:
        r = await client.get(
            "/api/v1/trips/999999999",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 404
        assert "not found" in (r.json().get("detail") or "").lower()
