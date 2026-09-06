"""Custody Slice 1 foundation: schema, terminals CRUD, reads, bootstrap, preflight, pointer safety."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import configure_mappers

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.custody import (
    CUSTODY_EVENT_BOOTSTRAP,
    CUSTODY_OWNER_TRIP,
    CUSTODY_OWNER_UNKNOWN,
    CUSTODY_PLACEMENT_ON_TRAILER,
    CUSTODY_PLACEMENT_UNKNOWN,
    CUSTODY_SOURCE_BOOTSTRAP,
)
from app.main import app
from app.models.load import Load
from app.services.load_custody import (
    CustodyBootstrapAnomaly,
    bootstrap_load_custody_for_tenant,
    preflight_custody_bootstrap_anomalies,
)
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (
    os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
)
AUTH_HEADERS = {"host": "pytest.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")

SNAPSHOT_DTO_KEYS = {
    "load_id",
    "custody_owner",
    "custody_trip_id",
    "custody_terminal_id",
    "custody_placement",
    "custody_trailer_id",
    "custody_since_at",
    "last_custody_event_id",
}


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
    prefix = f"Y{uuid.uuid4().hex[:7].upper()}"
    r1 = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": prefix},
    )
    assert r1.status_code == 200, r1.text
    return prefix


async def _session():
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, Session


async def _pick_load_ids(client: AsyncClient, n: int = 1) -> list[int]:
    lr = await client.get("/api/v1/loads?page=1&size=20", headers=AUTH_HEADERS)
    if lr.status_code != 200:
        return []
    items = lr.json().get("items") or []
    return [int(x["id"]) for x in items[:n]]


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


async def _clear_open_memberships(load_id: int) -> None:
    engine, Session = await _session()
    try:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE trip_loads SET removed_at = NOW(), status_within_trip = 'removed', "
                    "completed_at = NULL "
                    "WHERE load_id = :lid AND removed_at IS NULL AND completed_at IS NULL "
                    "AND status_within_trip IN ('planned', 'active')"
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


async def _tenant_id_for_load(load_id: int) -> int:
    engine, Session = await _session()
    try:
        async with Session() as session:
            return int(
                (
                    await session.execute(
                        text("SELECT tenant_id FROM loads WHERE id = :lid"),
                        {"lid": load_id},
                    )
                ).scalar()
            )
    finally:
        await engine.dispose()


async def _load_guard_fields(load_id: int) -> dict:
    engine, Session = await _session()
    try:
        async with Session() as session:
            return dict(
                (
                    await session.execute(
                        text(
                            "SELECT status, current_location, active_dispatch_trip_id, trip_number, "
                            "active_trip_id FROM loads WHERE id = :lid"
                        ),
                        {"lid": load_id},
                    )
                )
                .mappings()
                .one()
            )
    finally:
        await engine.dispose()


async def _trip_load_fingerprint(load_id: int) -> list[dict]:
    engine, Session = await _session()
    try:
        async with Session() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT id, trip_id, status_within_trip, completed_at, removed_at "
                        "FROM trip_loads WHERE load_id = :lid ORDER BY id"
                    ),
                    {"lid": load_id},
                )
            ).mappings().all()
            return [dict(r) for r in rows]
    finally:
        await engine.dispose()


async def _reset_custody_snapshot(load_id: int) -> None:
    engine, Session = await _session()
    try:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE loads SET custody_owner = 'unknown', custody_trip_id = NULL, "
                    "custody_terminal_id = NULL, custody_placement = 'unknown', "
                    "custody_trailer_id = NULL, custody_since_at = NULL, "
                    "last_custody_event_id = NULL WHERE id = :lid"
                ),
                {"lid": load_id},
            )
            await session.execute(
                text(
                    "DELETE FROM load_custody_events WHERE load_id = :lid "
                    "AND event_type = 'custody_bootstrap'"
                ),
                {"lid": load_id},
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _make_active_membership(
    client: AsyncClient, load_id: int, *, with_trailer: bool = True
) -> tuple[int, int]:
    """Return (trip_id, tenant_id) with open ACTIVE membership."""
    await _clear_open_memberships(load_id)
    ids = await _first_driver_truck_trailer(client)
    if ids is None:
        pytest.skip("no driver/truck/trailer")
    d_id, t_id, r_id = ids
    r = await client.post(
        "/api/v1/trips",
        headers=AUTH_HEADERS,
        json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
    )
    assert r.status_code == 201, r.text
    trip_id = int(r.json()["id"])
    assign = {"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id}
    assert (
        await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json=assign,
        )
    ).status_code == 200
    await _reset_custody_snapshot(load_id)
    # Slice 2: membership activation requires accept-custody
    assert (
        await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody",
            headers=AUTH_HEADERS,
            json={},
        )
    ).status_code == 200
    if not with_trailer:
        # Accept requires trailer; clear after for placement=unknown bootstrap case.
        engine, Session = await _session()
        try:
            async with Session() as session:
                await session.execute(
                    text("UPDATE trips SET trailer_id = NULL WHERE id = :tid"),
                    {"tid": trip_id},
                )
                await session.commit()
        finally:
            await engine.dispose()
    return trip_id, await _tenant_id_for_load(load_id)


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestCustodyFoundationSlice1:
    async def test_load_trailer_orm_relationships_disambiguated(self):
        configure_mappers()
        assert {c.key for c in Load.trailer.property.local_columns} == {"trailer_id"}
        assert {c.key for c in Load.custody_trailer.property.local_columns} == {
            "custody_trailer_id"
        }
        assert {c.key for c in Load.active_trip.property.local_columns} == {"active_trip_id"}
        assert {c.key for c in Load.custody_trip.property.local_columns} == {"custody_trip_id"}

    async def test_terminal_crud_and_tenant_isolation(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        name = f"Yard-{uuid.uuid4().hex[:8]}"
        created = await client.post(
            "/api/v1/terminals",
            headers=AUTH_HEADERS,
            json={"name": name, "city": "Hamilton"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        tid = int(body["id"])
        assert body["name"] == name
        assert body["is_active"] is True
        tenant_id = int(body["tenant_id"])

        got = await client.get(f"/api/v1/terminals/{tid}", headers=AUTH_HEADERS)
        assert got.status_code == 200
        assert got.json()["id"] == tid

        listed = await client.get("/api/v1/terminals", headers=AUTH_HEADERS)
        assert listed.status_code == 200
        assert any(x["id"] == tid for x in listed.json()["items"])

        # Isolation: foreign-tenant terminal must not appear
        engine, Session = await _session()
        try:
            async with Session() as session:
                foreign_name = f"Foreign-{uuid.uuid4().hex[:8]}"
                foreign_tenant = tenant_id + 9_000_001
                await session.execute(
                    text(
                        "INSERT INTO terminals (tenant_id, name, is_active) "
                        "VALUES (:tn, :nm, true)"
                    ),
                    {"tn": foreign_tenant, "nm": foreign_name},
                )
                await session.commit()
        finally:
            await engine.dispose()

        listed2 = await client.get("/api/v1/terminals?active_only=false", headers=AUTH_HEADERS)
        assert listed2.status_code == 200
        assert all(int(x["tenant_id"]) == tenant_id for x in listed2.json()["items"])
        assert all(x["name"] != foreign_name for x in listed2.json()["items"])

        patched = await client.patch(
            f"/api/v1/terminals/{tid}",
            headers=AUTH_HEADERS,
            json={"city": "Toronto", "is_active": False},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["city"] == "Toronto"
        assert patched.json()["is_active"] is False

        active_only = await client.get("/api/v1/terminals", headers=AUTH_HEADERS)
        assert all(x["id"] != tid for x in active_only.json()["items"])
        all_rows = await client.get("/api/v1/terminals?active_only=false", headers=AUTH_HEADERS)
        assert any(x["id"] == tid and x["is_active"] is False for x in all_rows.json()["items"])

    async def test_custody_snapshot_full_dto_and_event_ordering(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id)
        await _reset_custody_snapshot(load_id)

        engine, Session = await _session()
        try:
            async with Session() as session:
                t0 = datetime.now(timezone.utc) - timedelta(hours=2)
                t1 = datetime.now(timezone.utc) - timedelta(hours=1)
                # Seed two bootstrap-shaped rows with intentional out-of-id order timestamps
                await session.execute(
                    text(
                        "INSERT INTO load_custody_events "
                        "(tenant_id, load_id, event_type, occurred_at, recorded_at, "
                        "custody_owner_after, placement_after, trip_id, source, notes, "
                        "idempotency_key) VALUES "
                        "(:tn, :lid, 'custody_bootstrap', :t1, :t1, 'trip', 'unknown', :trip, "
                        "'bootstrap', 'later', 'order-test-later'), "
                        "(:tn, :lid, 'custody_bootstrap', :t0, :t0, 'trip', 'unknown', :trip, "
                        "'bootstrap', 'earlier', 'order-test-earlier')"
                    ),
                    {"tn": tenant_id, "lid": load_id, "trip": trip_id, "t0": t0, "t1": t1},
                )
                await session.commit()
        finally:
            await engine.dispose()

        snap = await client.get(f"/api/v1/loads/{load_id}/custody", headers=AUTH_HEADERS)
        assert snap.status_code == 200
        assert set(snap.json().keys()) == SNAPSHOT_DTO_KEYS
        assert snap.json()["load_id"] == load_id

        ev = await client.get(f"/api/v1/loads/{load_id}/custody-events", headers=AUTH_HEADERS)
        assert ev.status_code == 200
        items = ev.json()["items"]
        assert len(items) >= 2
        notes = [x["notes"] for x in items if x.get("notes") in ("earlier", "later")]
        assert notes == ["earlier", "later"]
        times = [x["occurred_at"] for x in items]
        assert times == sorted(times)

    async def test_bootstrap_active_with_trailer_on_trailer(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id, with_trailer=True)
        await _reset_custody_snapshot(load_id)
        before = await _load_guard_fields(load_id)
        tl_before = await _trip_load_fingerprint(load_id)

        engine, Session = await _session()
        try:
            async with Session() as session:
                before_boot = datetime.now(timezone.utc)
                summary = await bootstrap_load_custody_for_tenant(
                    session, tenant_id, dry_run=False, load_ids=[load_id]
                )
                after_boot = datetime.now(timezone.utc)
                await session.commit()
                assert summary["bootstrapped"] >= 1
                snap = (
                    await session.execute(
                        text(
                            "SELECT custody_owner, custody_trip_id, custody_placement, "
                            "custody_trailer_id, custody_since_at, last_custody_event_id "
                            "FROM loads WHERE id = :lid"
                        ),
                        {"lid": load_id},
                    )
                ).mappings().one()
                assert snap["custody_owner"] == CUSTODY_OWNER_TRIP
                assert int(snap["custody_trip_id"]) == trip_id
                assert snap["custody_placement"] == CUSTODY_PLACEMENT_ON_TRAILER
                assert snap["custody_trailer_id"] is not None
                ev = (
                    await session.execute(
                        text(
                            "SELECT event_type, source, occurred_at, recorded_at, notes "
                            "FROM load_custody_events WHERE id = :eid"
                        ),
                        {"eid": int(snap["last_custody_event_id"])},
                    )
                ).mappings().one()
                assert ev["event_type"] == CUSTODY_EVENT_BOOTSTRAP
                assert ev["source"] == CUSTODY_SOURCE_BOOTSTRAP
                assert "not a historical pickup" in (ev["notes"] or "").lower()
                for col in ("occurred_at", "recorded_at"):
                    ts = ev[col]
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    assert before_boot - timedelta(seconds=5) <= ts <= after_boot + timedelta(seconds=5)

                summary2 = await bootstrap_load_custody_for_tenant(
                    session, tenant_id, dry_run=False, load_ids=[load_id]
                )
                await session.commit()
                assert summary2["skipped_idempotent"] >= 1
                n = (
                    await session.execute(
                        text(
                            "SELECT count(*)::int FROM load_custody_events "
                            "WHERE load_id = :lid AND event_type = 'custody_bootstrap' "
                            "AND source = 'bootstrap' AND notes LIKE '%not a historical pickup%'"
                        ),
                        {"lid": load_id},
                    )
                ).scalar()
                assert int(n) == 1
        finally:
            await engine.dispose()

        after = await _load_guard_fields(load_id)
        assert after["status"] == before["status"]
        assert after["current_location"] == before["current_location"]
        assert after["active_dispatch_trip_id"] == before["active_dispatch_trip_id"]
        assert after["trip_number"] == before["trip_number"]
        assert await _trip_load_fingerprint(load_id) == tl_before

    async def test_bootstrap_active_without_trailer_unknown_placement(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id, with_trailer=False)
        await _reset_custody_snapshot(load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                summary = await bootstrap_load_custody_for_tenant(
                    session, tenant_id, dry_run=False, load_ids=[load_id]
                )
                await session.commit()
                assert summary["bootstrapped"] >= 1
                snap = (
                    await session.execute(
                        text(
                            "SELECT custody_owner, custody_trip_id, custody_placement, "
                            "custody_trailer_id FROM loads WHERE id = :lid"
                        ),
                        {"lid": load_id},
                    )
                ).mappings().one()
                assert snap["custody_owner"] == CUSTODY_OWNER_TRIP
                assert int(snap["custody_trip_id"]) == trip_id
                assert snap["custody_placement"] == CUSTODY_PLACEMENT_UNKNOWN
                assert snap["custody_trailer_id"] is None
        finally:
            await engine.dispose()

    async def test_no_active_remains_unknown_no_bootstrap_event(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        await _reset_custody_snapshot(load_id)
        tenant_id = await _tenant_id_for_load(load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                summary = await bootstrap_load_custody_for_tenant(
                    session, tenant_id, dry_run=False, load_ids=[load_id]
                )
                await session.commit()
                assert summary["bootstrapped"] == 0
                assert summary["active_memberships_seen"] == 0
                snap = (
                    await session.execute(
                        text(
                            "SELECT custody_owner, last_custody_event_id FROM loads WHERE id = :lid"
                        ),
                        {"lid": load_id},
                    )
                ).mappings().one()
                assert snap["custody_owner"] == CUSTODY_OWNER_UNKNOWN
                assert snap["last_custody_event_id"] is None
                n = (
                    await session.execute(
                        text(
                            "SELECT count(*)::int FROM load_custody_events "
                            "WHERE load_id = :lid AND event_type = 'custody_bootstrap'"
                        ),
                        {"lid": load_id},
                    )
                ).scalar()
                assert int(n) == 0
        finally:
            await engine.dispose()

    async def test_preflight_multiple_open_active_stop(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        _trip_a, tenant_id = await _make_active_membership(client, load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                # DB normally forbids >1 OPEN ACTIVE; drop unique constraint inside an
                # uncommitted transaction so preflight STOP can be exercised, then rollback.
                await session.execute(
                    text("DROP INDEX IF EXISTS uq_trip_loads_one_open_active_per_load")
                )
                trip_b = (
                    await session.execute(
                        text(
                            "INSERT INTO trips (tenant_id, status, job_type, trip_number) "
                            "VALUES (:tn, 'planned', 'freight_load', :tnr) RETURNING id"
                        ),
                        {"tn": tenant_id, "tnr": f"X{uuid.uuid4().hex[:10].upper()}"},
                    )
                ).scalar()
                await session.execute(
                    text(
                        "INSERT INTO trip_loads (tenant_id, trip_id, load_id, status_within_trip) "
                        "VALUES (:tn, :tid, :lid, 'active')"
                    ),
                    {"tn": tenant_id, "tid": int(trip_b), "lid": load_id},
                )
                with pytest.raises(CustodyBootstrapAnomaly) as ei:
                    await preflight_custody_bootstrap_anomalies(
                        session, tenant_id=tenant_id, load_ids=[load_id]
                    )
                assert ei.value.code == "MULTIPLE_OPEN_ACTIVE_MEMBERSHIPS"
                await session.rollback()
        finally:
            await engine.dispose()

    async def test_preflight_wrong_nonnull_active_trip_id_stop(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                other = (
                    await session.execute(
                        text(
                            "INSERT INTO trips (tenant_id, status, job_type, trip_number) "
                            "VALUES (:tn, 'planned', 'freight_load', :tnr) RETURNING id"
                        ),
                        {"tn": tenant_id, "tnr": f"W{uuid.uuid4().hex[:10].upper()}"},
                    )
                ).scalar()
                await session.execute(
                    text("UPDATE loads SET active_trip_id = :w WHERE id = :lid"),
                    {"w": int(other), "lid": load_id},
                )
                await session.commit()
                with pytest.raises(CustodyBootstrapAnomaly) as ei:
                    await preflight_custody_bootstrap_anomalies(
                        session, tenant_id=tenant_id, load_ids=[load_id]
                    )
                assert ei.value.code == "ACTIVE_TRIP_ID_MISMATCH"
                await session.execute(
                    text("UPDATE loads SET active_trip_id = :tid WHERE id = :lid"),
                    {"tid": trip_id, "lid": load_id},
                )
                await session.commit()
        finally:
            await engine.dispose()

    async def test_preflight_null_pointer_with_active_stop(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                await session.execute(
                    text("UPDATE loads SET active_trip_id = NULL WHERE id = :lid"),
                    {"lid": load_id},
                )
                await session.commit()
                with pytest.raises(CustodyBootstrapAnomaly) as ei:
                    await preflight_custody_bootstrap_anomalies(
                        session, tenant_id=tenant_id, load_ids=[load_id]
                    )
                assert ei.value.code == "ACTIVE_TRIP_ID_MISMATCH"
                await session.execute(
                    text("UPDATE loads SET active_trip_id = :tid WHERE id = :lid"),
                    {"lid": load_id, "tid": trip_id},
                )
                await session.commit()
        finally:
            await engine.dispose()

    async def test_preflight_pointer_with_no_active_stop(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                await session.execute(
                    text(
                        "UPDATE trip_loads SET removed_at = NOW(), status_within_trip = 'removed' "
                        "WHERE load_id = :lid AND trip_id = :tid AND status_within_trip = 'active' "
                        "AND completed_at IS NULL AND removed_at IS NULL"
                    ),
                    {"lid": load_id, "tid": trip_id},
                )
                await session.execute(
                    text("UPDATE loads SET active_trip_id = :tid WHERE id = :lid"),
                    {"tid": trip_id, "lid": load_id},
                )
                await session.commit()
                with pytest.raises(CustodyBootstrapAnomaly) as ei:
                    await preflight_custody_bootstrap_anomalies(
                        session, tenant_id=tenant_id, load_ids=[load_id]
                    )
                assert ei.value.code == "ACTIVE_TRIP_ID_MISMATCH"
                await session.execute(
                    text("UPDATE loads SET active_trip_id = NULL WHERE id = :lid"),
                    {"lid": load_id},
                )
                await session.commit()
        finally:
            await engine.dispose()

    async def test_preflight_active_on_completed_trip_stop(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                await session.execute(
                    text("UPDATE trips SET status = 'completed' WHERE id = :tid"),
                    {"tid": trip_id},
                )
                await session.commit()
                with pytest.raises(CustodyBootstrapAnomaly) as ei:
                    await preflight_custody_bootstrap_anomalies(
                        session, tenant_id=tenant_id, load_ids=[load_id]
                    )
                assert ei.value.code == "ACTIVE_MEMBERSHIP_ON_TERMINAL_TRIP"
                await session.execute(
                    text("UPDATE trips SET status = 'in_progress' WHERE id = :tid"),
                    {"tid": trip_id},
                )
                await session.commit()
        finally:
            await engine.dispose()

    async def test_preflight_active_on_cancelled_trip_stop(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, tenant_id = await _make_active_membership(client, load_id)
        engine, Session = await _session()
        try:
            async with Session() as session:
                await session.execute(
                    text("UPDATE trips SET status = 'cancelled' WHERE id = :tid"),
                    {"tid": trip_id},
                )
                await session.commit()
                with pytest.raises(CustodyBootstrapAnomaly) as ei:
                    await preflight_custody_bootstrap_anomalies(
                        session, tenant_id=tenant_id, load_ids=[load_id]
                    )
                assert ei.value.code == "ACTIVE_MEMBERSHIP_ON_TERMINAL_TRIP"
                await session.execute(
                    text("UPDATE trips SET status = 'in_progress' WHERE id = :tid"),
                    {"tid": trip_id},
                )
                await session.commit()
        finally:
            await engine.dispose()

    async def test_bare_activate_closed_after_slice2(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        ids = await _first_driver_truck_trailer(client)
        if ids is None:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = ids
        created = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert created.status_code == 201, created.text
        trip_id = int(created.json()["id"])
        assert (
            await client.put(
                f"/api/v1/trips/{trip_id}/assignment",
                headers=AUTH_HEADERS,
                json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
            )
        ).status_code == 200
        act = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/activate",
            headers=AUTH_HEADERS,
        )
        assert act.status_code == 409
        assert act.json()["detail"]["code"] == "MEMBERSHIP_TRANSITION_REQUIRES_CUSTODY"

    async def test_bare_complete_closed_after_slice2(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        trip_id, _ = await _make_active_membership(client, load_id)
        done = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/complete",
            headers=AUTH_HEADERS,
        )
        assert done.status_code == 409
        assert done.json()["detail"]["code"] == "MEMBERSHIP_TRANSITION_REQUIRES_CUSTODY"
