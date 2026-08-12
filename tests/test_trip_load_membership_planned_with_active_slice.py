"""TripLoad open cardinality: ACTIVE A + PLANNED B; active_trip_id ACTIVE-only."""

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

from app.constants.trip_dispatch import (
    TRIP_LOAD_STATUS_WITHIN_ACTIVE,
    TRIP_LOAD_STATUS_WITHIN_PLANNED,
)
from app.main import app
from app.models.dispatch_trip import DispatchTrip
from app.models.load import Load
from app.services.dispatch_trips import _upsert_trip_and_membership
from app.services.trips import _insert_trip_load_row
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


async def _pick_load_id(client: AsyncClient) -> int | None:
    lr = await client.get("/api/v1/loads?page=1&size=5", headers=AUTH_HEADERS)
    if lr.status_code != 200:
        return None
    items = lr.json().get("items") or []
    if not items:
        return None
    return int(items[0]["id"])


async def _clear_open_memberships(load_id: int) -> None:
    """Isolate tests that share demo loads (soft-remove open trip_loads + clear pointer)."""
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE trip_loads SET removed_at = NOW(), status_within_trip = 'removed' "
                    "WHERE load_id = :lid AND removed_at IS NULL"
                ),
                {"lid": load_id},
            )
            await session.execute(
                text("UPDATE loads SET active_trip_id = NULL WHERE id = :lid"),
                {"lid": load_id},
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _promote_membership_active(load_id: int, trip_id: int) -> None:
    """Trip HTTP path only creates planned memberships; promote for ACTIVE A fixtures."""
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE trip_loads SET status_within_trip = :st "
                    "WHERE load_id = :lid AND trip_id = :tid AND removed_at IS NULL"
                ),
                {"st": TRIP_LOAD_STATUS_WITHIN_ACTIVE, "lid": load_id, "tid": trip_id},
            )
            await session.execute(
                text("UPDATE loads SET active_trip_id = :tid WHERE id = :lid"),
                {"tid": trip_id, "lid": load_id},
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _membership_rows(load_id: int) -> list[dict]:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT trip_id, status_within_trip, removed_at IS NULL AS is_open "
                        "FROM trip_loads WHERE load_id = :lid ORDER BY id"
                    ),
                    {"lid": load_id},
                )
            ).mappings().all()
            return [dict(r) for r in rows]
    finally:
        await engine.dispose()


async def _load_active_trip_id(load_id: int) -> int | None:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            return (
                await session.execute(
                    text("SELECT active_trip_id FROM loads WHERE id = :lid"),
                    {"lid": load_id},
                )
            ).scalar()
    finally:
        await engine.dispose()


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestTripLoadPlannedWithActiveSlice:
    async def test_active_a_plus_planned_b_allowed_pointer_stays_a(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        load_id = await _pick_load_id(client)
        if load_id is None:
            pytest.skip("no loads")
        await _clear_open_memberships(load_id)

        r_a = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_a.status_code == 201, r_a.text
        trip_a = int(r_a.json()["id"])
        await _promote_membership_active(load_id, trip_a)
        assert await _load_active_trip_id(load_id) == trip_a

        r_b = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_b.status_code == 201, r_b.text
        trip_b = int(r_b.json()["id"])
        assert await _load_active_trip_id(load_id) == trip_a

        rows = await _membership_rows(load_id)
        open_rows = [r for r in rows if r["is_open"]]
        by_trip = {int(r["trip_id"]): r["status_within_trip"] for r in open_rows}
        assert by_trip.get(trip_a) == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        assert by_trip.get(trip_b) == TRIP_LOAD_STATUS_WITHIN_PLANNED

        # No Trip execution side effect from planned attach
        detail_a = await client.get(f"/api/v1/trips/{trip_a}", headers=AUTH_HEADERS)
        detail_b = await client.get(f"/api/v1/trips/{trip_b}", headers=AUTH_HEADERS)
        assert detail_a.status_code == 200 and detail_b.status_code == 200
        assert (detail_a.json().get("status") or "").lower() != "in_progress"
        assert (detail_b.json().get("status") or "").lower() == "planned"

    async def test_second_open_planned_rejected(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        load_id = await _pick_load_id(client)
        if load_id is None:
            pytest.skip("no loads")
        await _clear_open_memberships(load_id)

        r_a = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_a.status_code == 201, r_a.text
        trip_a = int(r_a.json()["id"])
        await _promote_membership_active(load_id, trip_a)

        r_b = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_b.status_code == 201, r_b.text

        r_c = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_c.status_code == 409, r_c.text
        assert r_c.json().get("detail", {}).get("code") == "LOAD_PLANNED_ON_OTHER_TRIP"

    async def test_second_open_active_rejected_trip_api_and_legacy(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        url = _tenant_async_url()
        if not url:
            pytest.skip("no tenant db")
        load_id = await _pick_load_id(client)
        if load_id is None:
            pytest.skip("no loads")
        await _clear_open_memberships(load_id)

        r_a = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_a.status_code == 201, r_a.text
        trip_a = int(r_a.json()["id"])
        await _promote_membership_active(load_id, trip_a)

        r_b = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_b.status_code == 201, r_b.text
        trip_b = int(r_b.json()["id"])

        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                row = (
                    await session.execute(
                        text("SELECT tenant_id FROM loads WHERE id = :lid"),
                        {"lid": load_id},
                    )
                ).first()
                assert row is not None
                tenant_id = int(row[0])

                from fastapi import HTTPException

                with pytest.raises(HTTPException) as ei:
                    await _insert_trip_load_row(
                        session,
                        tenant_id,
                        trip_b,
                        load_id,
                        sequence_hint=None,
                        status_within=TRIP_LOAD_STATUS_WITHIN_ACTIVE,
                    )
                assert ei.value.status_code == 409
                assert ei.value.detail["code"] == "LOAD_ACTIVE_ON_OTHER_TRIP"
                await session.rollback()

                # Legacy mirror path: second ACTIVE blocked; open PLANNED on B must not be overwritten.
                load = await session.get(Load, load_id)
                assert load is not None
                d_trip = DispatchTrip(
                    tenant_id=tenant_id,
                    trip_number=f"LEG{uuid.uuid4().hex[:8].upper()}",
                    job_type="freight_load",
                    status="active",
                    load_id=load_id,
                    trailer_move_id=None,
                )
                session.add(d_trip)
                await session.flush()
                with pytest.raises(HTTPException) as ej:
                    await _upsert_trip_and_membership(session, tenant_id, load_id, d_trip, load)
                assert ej.value.status_code == 409
                assert ej.value.detail["code"] == "LOAD_ACTIVE_ON_OTHER_TRIP"
                await session.rollback()
        finally:
            await engine.dispose()

        assert await _load_active_trip_id(load_id) == trip_a

    async def test_planned_only_leaves_active_trip_id_null(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        load_id = await _pick_load_id(client)
        if load_id is None:
            pytest.skip("no loads")
        await _clear_open_memberships(load_id)

        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r.status_code == 201, r.text
        assert await _load_active_trip_id(load_id) is None
        rows = await _membership_rows(load_id)
        open_planned = [
            r
            for r in rows
            if r["is_open"] and r["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_PLANNED
        ]
        assert len(open_planned) == 1

    async def test_remove_and_cancel_planned_b_leaves_active_a(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        load_id = await _pick_load_id(client)
        if load_id is None:
            pytest.skip("no loads")
        await _clear_open_memberships(load_id)

        r_a = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_a.status_code == 201, r_a.text
        trip_a = int(r_a.json()["id"])
        await _promote_membership_active(load_id, trip_a)

        r_b = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_b.status_code == 201, r_b.text
        trip_b = int(r_b.json()["id"])

        r_rm = await client.post(
            f"/api/v1/trips/{trip_b}/loads/{load_id}/remove",
            headers=AUTH_HEADERS,
        )
        assert r_rm.status_code == 200, r_rm.text
        assert await _load_active_trip_id(load_id) == trip_a
        rows = await _membership_rows(load_id)
        assert any(
            int(r["trip_id"]) == trip_a
            and r["is_open"]
            and r["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
            for r in rows
        )

        # Re-attach planned B then cancel trip B
        r_b2 = await client.post(
            f"/api/v1/trips/{trip_b}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": load_id},
        )
        # trip_b may be cancelled? No, we only removed membership. Cancel trip B.
        if r_b2.status_code != 200:
            # create new planned trip C instead
            r_c = await client.post(
                "/api/v1/trips",
                headers=AUTH_HEADERS,
                json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
            )
            assert r_c.status_code == 201, r_c.text
            trip_cancel = int(r_c.json()["id"])
        else:
            trip_cancel = trip_b

        r_cancel = await client.post(f"/api/v1/trips/{trip_cancel}/cancel", headers=AUTH_HEADERS)
        assert r_cancel.status_code == 200, r_cancel.text
        assert await _load_active_trip_id(load_id) == trip_a
        rows2 = await _membership_rows(load_id)
        assert any(
            int(r["trip_id"]) == trip_a
            and r["is_open"]
            and r["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
            for r in rows2
        )

    async def test_same_trip_duplicate_rejected(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        load_id = await _pick_load_id(client)
        if load_id is None:
            pytest.skip("no loads")
        await _clear_open_memberships(load_id)

        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r.status_code == 201, r.text
        trip_id = int(r.json()["id"])

        r2 = await client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": load_id},
        )
        assert r2.status_code == 409, r2.text
        assert r2.json().get("detail", {}).get("code") == "DUPLICATE_TRIP_LOAD_MEMBERSHIP"
