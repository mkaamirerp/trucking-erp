"""Phase 3D: POST trips (planned), add/remove trip_loads, cancel trip — API + service checks."""

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

from app.constants.trip_dispatch import TRIP_CONTAINER_STATUS_CANCELLED, TRIP_CONTAINER_STATUS_PLANNED
from app.main import app
from app.models.trip import Trip
from app.services.dispatch_trips import TRIP_LOAD_STATUS_WITHIN_REMOVED, mint_next_trip_number
from app.services.trips import create_planned_trip
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


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
class TestPhase3dServiceMintAndCreate:
    """Direct service tests against tenant DB (no HTTP platform DB required)."""

    @pytest.mark.asyncio
    async def test_missing_prefix_blocks_mint(self) -> None:
        url = _tenant_async_url()
        assert url
        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                row = (await session.execute(text("SELECT DISTINCT tenant_id FROM loads LIMIT 1"))).first()
                if row is None:
                    row = (await session.execute(text("SELECT DISTINCT tenant_id FROM drivers LIMIT 1"))).first()
                if row is None:
                    pytest.skip("no tenant row")
                tenant_id = int(row[0])
                from unittest.mock import patch

                async def _no_row(*_a, **_k):
                    return None

                with patch("app.services.dispatch_trips.get_or_create_numbering_for_update", _no_row):
                    with pytest.raises(Exception) as exc:
                        await mint_next_trip_number(session, tenant_id)
                    assert getattr(exc.value, "status_code", None) == 409
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_create_planned_trip_zero_loads_sequence_bumps(self) -> None:
        url = _tenant_async_url()
        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                row = (await session.execute(text("SELECT DISTINCT tenant_id FROM loads LIMIT 1"))).first()
                if row is None:
                    row = (await session.execute(text("SELECT DISTINCT tenant_id FROM drivers LIMIT 1"))).first()
                if row is None:
                    pytest.skip("no tenant")
                tenant_id = int(row[0])
                n0 = (
                    await session.execute(
                        text("SELECT next_numeric FROM tenant_dispatch_numbering WHERE tenant_id = :tid"),
                        {"tid": tenant_id},
                    )
                ).scalar()
                if n0 is None:
                    pytest.skip("tenant_dispatch_numbering missing")
                n0 = int(n0)
                d0 = await create_planned_trip(session, tenant_id, load_ids=[])
                await session.commit()
                assert d0.member_loads == []
                assert d0.status == TRIP_CONTAINER_STATUS_PLANNED
                n1 = (
                    await session.execute(
                        text("SELECT next_numeric FROM tenant_dispatch_numbering WHERE tenant_id = :tid"),
                        {"tid": tenant_id},
                    )
                ).scalar()
                assert int(n1) == n0 + 1
                tr = await session.get(Trip, d0.id)
                assert tr is not None
                assert tr.legacy_dispatch_trip_id is None
        finally:
            await engine.dispose()


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestPhase3dHttp:
    async def test_http_create_add_remove_cancel(self, client: AsyncClient, locked_prefix: str, override_auth_tenant):
        u = uuid.uuid4().hex[:8]
        r_create = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_create.status_code == 201, r_create.text
        trip = r_create.json()
        trip_id = int(trip["id"])
        assert trip["trip_number"].startswith(locked_prefix[:3]) or trip["trip_number"].startswith(locked_prefix[0])
        assert trip["status"] == "planned"
        assert trip["cancelled_at"] is None

        # pick a load without active trip_loads on another trip (best-effort: any load id)
        # Use list loads API
        lr = await client.get("/api/v1/loads?page=1&size=5", headers=AUTH_HEADERS)
        assert lr.status_code == 200
        items = lr.json().get("items") or []
        if not items:
            pytest.skip("no loads in tenant")
        load_id = int(items[0]["id"])

        r_add = await client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": load_id, "sequence_hint": 1},
        )
        if r_add.status_code == 409:
            pytest.skip("load already on another trip: %s" % r_add.text)
        assert r_add.status_code == 200, r_add.text
        assert any(m["load_id"] == load_id for m in r_add.json()["member_loads"])

        r_dup = await client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": load_id},
        )
        assert r_dup.status_code == 409

        r_rm = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/remove",
            headers=AUTH_HEADERS,
        )
        assert r_rm.status_code == 200
        for m in r_rm.json()["member_loads"]:
            if m["load_id"] == load_id:
                assert m["removed_at"] is not None
                assert m["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_REMOVED

        r_add2 = await client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": load_id},
        )
        assert r_add2.status_code == 200

        detail_before = await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)
        ln_before = detail_before.json()["trip_number"]

        r_cancel = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=AUTH_HEADERS)
        assert r_cancel.status_code == 200, r_cancel.text
        body = r_cancel.json()
        assert body["status"] == TRIP_CONTAINER_STATUS_CANCELLED
        assert body["trip_number"] == ln_before
        assert body["cancelled_at"] is not None

        r_cancel2 = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=AUTH_HEADERS)
        assert r_cancel2.status_code == 409

        still = await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)
        assert still.status_code == 200
        assert still.json()["status"] == TRIP_CONTAINER_STATUS_CANCELLED
