"""POST /trips/{id}/complete — Trip container closeout slice."""

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

from app.constants.trip_dispatch import TRIP_CONTAINER_STATUS_COMPLETED, TRIP_CONTAINER_STATUS_IN_PROGRESS
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.custody_http import activate_via_custody, complete_via_custody, ensure_active_terminal


REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "demo.truckerp.me"}
_SLICE2_TERMINAL: int | None = None

async def _terminal(client):
    global _SLICE2_TERMINAL
    if _SLICE2_TERMINAL is None:
        _SLICE2_TERMINAL = await ensure_active_terminal(client, AUTH_HEADERS)
    return _SLICE2_TERMINAL

async def _activate(client, trip_id, load_id):
    return await activate_via_custody(client, AUTH_HEADERS, trip_id, load_id)

async def _complete_mem(client, trip_id, load_id):
    return await complete_via_custody(client, AUTH_HEADERS, trip_id, load_id, terminal_id=await _terminal(client))

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
    prefix = f"C{uuid.uuid4().hex[:7].upper()}"
    r1 = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": prefix},
    )
    assert r1.status_code == 200, r1.text
    return prefix


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
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
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
                text(
                    "UPDATE loads SET active_trip_id = NULL, custody_owner = 'unknown', "
                    "custody_trip_id = NULL, custody_terminal_id = NULL, "
                    "custody_placement = 'unknown', custody_trailer_id = NULL, "
                    "custody_since_at = NULL, last_custody_event_id = NULL "
                    "WHERE id = :lid"
                ),
                {"lid": load_id},
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _load_row(load_id: int) -> dict:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text("SELECT status, active_trip_id FROM loads WHERE id = :lid"),
                    {"lid": load_id},
                )
            ).mappings().first()
            assert row is not None
            return dict(row)
    finally:
        await engine.dispose()


async def _trip_db(trip_id: int) -> dict:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, completed_at, cancelled_at, updated_at "
                        "FROM trips WHERE id = :tid"
                    ),
                    {"tid": trip_id},
                )
            ).mappings().first()
            assert row is not None
            return dict(row)
    finally:
        await engine.dispose()


async def _force_trip_status(trip_id: int, status: str) -> None:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE trips SET status = :st, completed_at = NULL, cancelled_at = NULL "
                    "WHERE id = :tid"
                ),
                {"tid": trip_id, "st": status},
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _force_open_active_on_completed(trip_id: int, load_id: int) -> None:
    """Test-only corruption: completed Trip + OPEN ACTIVE membership (no product API path)."""
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE trip_loads SET status_within_trip = 'active', completed_at = NULL, "
                    "removed_at = NULL WHERE trip_id = :tid AND load_id = :lid"
                ),
                {"tid": trip_id, "lid": load_id},
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _audit_count(action: str, trip_id: int) -> int | None:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            try:
                n = (
                    await session.execute(
                        text(
                            "SELECT count(*)::int FROM audit_events WHERE entity_type = 'trip' "
                            "AND entity_id = :eid AND action = :act"
                        ),
                        {"eid": str(trip_id), "act": action},
                    )
                ).scalar()
                return int(n or 0)
            except Exception:
                return None
    finally:
        await engine.dispose()


async def _assign_and_start(client: AsyncClient, trip_id: int) -> None:
    ids = await _first_driver_truck_trailer(client)
    if ids is None:
        pytest.skip("no driver/truck/trailer")
    d_id, t_id, r_id = ids
    r = await client.put(
        f"/api/v1/trips/{trip_id}/assignment",
        headers=AUTH_HEADERS,
        json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
    )
    assert r.status_code == 200, r.text
    r2 = await client.post(
        f"/api/v1/trips/{trip_id}/execution-signal",
        headers=AUTH_HEADERS,
        json={"source": "dispatcher_manual"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS


async def _create_in_progress_empty(client: AsyncClient) -> int:
    r = await client.post(
        "/api/v1/trips",
        headers=AUTH_HEADERS,
        json={"status": "planned", "job_type": "freight_load", "load_ids": []},
    )
    assert r.status_code == 201, r.text
    trip_id = int(r.json()["id"])
    await _assign_and_start(client, trip_id)
    return trip_id


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestTripCompleteSlice:
    async def test_in_progress_zero_open_completes_and_idempotent(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        trip_id = await _create_in_progress_empty(client)
        before_aud = await _audit_count("trip_completed", trip_id)

        r1 = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["status"] == TRIP_CONTAINER_STATUS_COMPLETED
        assert body1.get("completed_at") is not None
        stamp = body1["completed_at"]
        db1 = await _trip_db(trip_id)
        assert db1["status"] == "completed"
        assert db1["completed_at"] is not None
        assert db1["cancelled_at"] is None

        after_aud = await _audit_count("trip_completed", trip_id)
        if before_aud is not None and after_aud is not None:
            assert after_aud == before_aud + 1

        updated_at_1 = db1["updated_at"]

        r2 = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "completed"
        assert r2.json()["completed_at"] == stamp
        db2 = await _trip_db(trip_id)
        assert db2["completed_at"] == db1["completed_at"]
        assert db2["updated_at"] == updated_at_1

        after2 = await _audit_count("trip_completed", trip_id)
        if after_aud is not None and after2 is not None:
            assert after2 == after_aud

    async def test_open_active_and_planned_gates(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)

        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r.status_code == 201, r.text
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id)
        assert (
            await _activate(client, trip_id, load_id)
        ).status_code == 200

        r_block = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r_block.status_code == 409
        assert r_block.json()["detail"]["code"] == "OPEN_ACTIVE_MEMBERSHIP_REMAINS"

        assert (
            await _complete_mem(client, trip_id, load_id)
        ).status_code == 200

        loads2 = await _pick_load_ids(client, 2)
        if len(loads2) < 2:
            pytest.skip("need second load for planned gate")
        other = loads2[1] if loads2[1] != load_id else (loads2[0] if loads2[0] != load_id else None)
        if other is None:
            pytest.skip("need distinct second load")
        await _clear_open_memberships(other)
        r_add = await client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": other},
        )
        assert r_add.status_code == 200, r_add.text
        r_pl = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r_pl.status_code == 409
        assert r_pl.json()["detail"]["code"] == "OPEN_PLANNED_MEMBERSHIP_REMAINS"

        assert (
            await client.post(
                f"/api/v1/trips/{trip_id}/loads/{other}/remove",
                headers=AUTH_HEADERS,
            )
        ).status_code == 200
        r_ok = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r_ok.status_code == 200, r_ok.text
        assert r_ok.json()["status"] == "completed"

    async def test_multi_load_complete_then_trip_complete_no_auto_activate(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 2)
        if len(loads) < 2:
            pytest.skip("need two loads")
        load_a, load_b = loads[0], loads[1]
        await _clear_open_memberships(load_a)
        await _clear_open_memberships(load_b)

        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_a, load_b]},
        )
        assert r.status_code == 201, r.text
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id)
        for lid in (load_a, load_b):
            assert (
                await _activate(client, trip_id, lid)
            ).status_code == 200

        status_a0 = (await _load_row(load_a))["status"]
        status_b0 = (await _load_row(load_b))["status"]

        assert (
            await _complete_mem(client, trip_id, load_a)
        ).status_code == 200
        assert (await _load_row(load_a))["active_trip_id"] is None
        assert (await _load_row(load_b))["active_trip_id"] == trip_id

        r_mid = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r_mid.status_code == 409
        assert r_mid.json()["detail"]["code"] == "OPEN_ACTIVE_MEMBERSHIP_REMAINS"

        r_out = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_a]},
        )
        assert r_out.status_code == 201, r_out.text
        outbound = int(r_out.json()["id"])

        assert (
            await _complete_mem(client, trip_id, load_b)
        ).status_code == 200
        ptr_b = (await _load_row(load_b))["active_trip_id"]
        ptr_a = (await _load_row(load_a))["active_trip_id"]

        r_done = await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        assert r_done.status_code == 200, r_done.text
        assert r_done.json()["status"] == "completed"

        assert (await _load_row(load_a))["status"] == status_a0
        assert (await _load_row(load_b))["status"] == status_b0
        assert (await _load_row(load_a))["active_trip_id"] == ptr_a
        assert (await _load_row(load_b))["active_trip_id"] == ptr_b
        assert (await _load_row(load_a))["active_trip_id"] != outbound

        det_out = await client.get(f"/api/v1/trips/{outbound}", headers=AUTH_HEADERS)
        assert det_out.status_code == 200
        assert det_out.json()["status"] == "planned"

    async def test_status_gates_planned_assigned_cancelled_legacy(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r.status_code == 201, r.text
        trip_planned = int(r.json()["id"])
        rp = await client.post(f"/api/v1/trips/{trip_planned}/complete", headers=AUTH_HEADERS)
        assert rp.status_code == 409
        assert rp.json()["detail"]["code"] == "INVALID_TRIP_STATUS_FOR_COMPLETE"

        r2 = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        trip_as = int(r2.json()["id"])
        ids = await _first_driver_truck_trailer(client)
        assert ids
        d_id, t_id, r_id = ids
        assert (
            await client.put(
                f"/api/v1/trips/{trip_as}/assignment",
                headers=AUTH_HEADERS,
                json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
            )
        ).status_code == 200
        ra = await client.post(f"/api/v1/trips/{trip_as}/complete", headers=AUTH_HEADERS)
        assert ra.status_code == 409
        assert ra.json()["detail"]["code"] == "INVALID_TRIP_STATUS_FOR_COMPLETE"

        trip_c = await _create_in_progress_empty(client)
        assert (await client.post(f"/api/v1/trips/{trip_c}/cancel", headers=AUTH_HEADERS)).status_code == 200
        rc = await client.post(f"/api/v1/trips/{trip_c}/complete", headers=AUTH_HEADERS)
        assert rc.status_code == 409
        assert rc.json()["detail"]["code"] == "TRIP_CANCELLED"
        assert (await _trip_db(trip_c))["completed_at"] is None

        trip_leg = await _create_in_progress_empty(client)
        await _force_trip_status(trip_leg, "active")
        rl = await client.post(f"/api/v1/trips/{trip_leg}/complete", headers=AUTH_HEADERS)
        assert rl.status_code == 409
        assert rl.json()["detail"]["code"] == "INVALID_TRIP_STATUS_FOR_COMPLETE"

    async def test_terminal_mutators_reject_completed(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)

        trip_id = await _create_in_progress_empty(client)
        assert (
            await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        ).status_code == 200

        r_add = await client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": load_id},
        )
        assert r_add.status_code == 409
        assert r_add.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

        r_rm = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/remove",
            headers=AUTH_HEADERS,
        )
        assert r_rm.status_code == 409
        assert r_rm.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

        r_act = await _activate(client, trip_id, load_id)
        assert r_act.status_code == 409
        assert r_act.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

        ids = await _first_driver_truck_trailer(client)
        assert ids
        d_id, t_id, r_id = ids
        r_asg = await client.put(
            f"/api/v1/trips/{trip_id}/assignment",
            headers=AUTH_HEADERS,
            json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
        )
        assert r_asg.status_code == 409
        assert r_asg.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

        r_sch = await client.put(
            f"/api/v1/trips/{trip_id}/schedule",
            headers=AUTH_HEADERS,
            json={"planned_start_at": None, "expected_completion_at": None},
        )
        assert r_sch.status_code == 409
        assert r_sch.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

        r_can = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=AUTH_HEADERS)
        assert r_can.status_code == 409
        assert r_can.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

        r_sig = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert r_sig.status_code == 409
        assert r_sig.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

    async def test_membership_complete_on_completed_trip_rules(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)

        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        trip_id = int(r.json()["id"])
        await _assign_and_start(client, trip_id)
        assert (
            await _activate(client, trip_id, load_id)
        ).status_code == 200
        assert (
            await _complete_mem(client, trip_id, load_id)
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/trips/{trip_id}/complete", headers=AUTH_HEADERS)
        ).status_code == 200

        r_idem = await _complete_mem(client, trip_id, load_id)
        assert r_idem.status_code == 409
        assert r_idem.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

        await _force_open_active_on_completed(trip_id, load_id)
        r_rep = await _complete_mem(client, trip_id, load_id)
        assert r_rep.status_code == 409
        assert r_rep.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

    async def test_serialization_add_then_complete_and_complete_then_add(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)

        trip_a = await _create_in_progress_empty(client)
        assert (
            await client.post(
                f"/api/v1/trips/{trip_a}/loads",
                headers=AUTH_HEADERS,
                json={"load_id": load_id},
            )
        ).status_code == 200
        r_blk = await client.post(f"/api/v1/trips/{trip_a}/complete", headers=AUTH_HEADERS)
        assert r_blk.status_code == 409
        assert r_blk.json()["detail"]["code"] == "OPEN_PLANNED_MEMBERSHIP_REMAINS"

        await _clear_open_memberships(load_id)
        trip_b = await _create_in_progress_empty(client)
        assert (
            await client.post(f"/api/v1/trips/{trip_b}/complete", headers=AUTH_HEADERS)
        ).status_code == 200
        r_add = await client.post(
            f"/api/v1/trips/{trip_b}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": load_id},
        )
        assert r_add.status_code == 409
        assert r_add.json()["detail"]["code"] == "TRIP_ALREADY_COMPLETED"

    async def test_insert_lock_order_trip_then_load_helper_present(self):
        """Source-level: membership insert locks Trip before Load; complete locks Trip."""
        from pathlib import Path

        from app.services import trips as trips_mod

        src = Path(trips_mod.__file__).read_text()
        insert_start = src.index("async def _insert_trip_load_row")
        insert_chunk = src[insert_start : insert_start + 1200]
        assert "_lock_trip_for_mutation" in insert_chunk
        assert insert_chunk.index("_lock_trip_for_mutation") < insert_chunk.index(
            "_lock_load_for_membership"
        )
        complete_start = src.index("async def complete_trip_container")
        complete_end = src.index("def _validate_execution_signal_source", complete_start)
        complete_chunk = src[complete_start:complete_end]
        assert "_lock_trip_for_mutation" in complete_chunk
        assert "OPEN_ACTIVE_MEMBERSHIP_REMAINS" in complete_chunk
        assert "OPEN_PLANNED_MEMBERSHIP_REMAINS" in complete_chunk