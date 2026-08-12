"""Explicit TripLoad transitions: planned→active, active→completed."""

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
    TRIP_LOAD_STATUS_WITHIN_COMPLETED,
    TRIP_LOAD_STATUS_WITHIN_PLANNED,
    TRIP_LOAD_STATUS_WITHIN_REMOVED,
)
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


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> str:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200
    body = r0.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"T{uuid.uuid4().hex[:7].upper()}"
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
                text("UPDATE loads SET active_trip_id = NULL WHERE id = :lid"),
                {"lid": load_id},
            )
            await session.commit()
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


async def _membership_row(load_id: int, trip_id: int) -> dict | None:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status_within_trip, completed_at, removed_at "
                        "FROM trip_loads WHERE load_id = :lid AND trip_id = :tid "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {"lid": load_id, "tid": trip_id},
                )
            ).mappings().first()
            return dict(row) if row else None
    finally:
        await engine.dispose()


async def _assign_trip(client: AsyncClient, trip_id: int) -> None:
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
    assert r.json()["status"] == "assigned"


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestTripLoadMembershipTransitions:
    async def test_activate_complete_flow_and_gates(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 2)
        if len(loads) < 1:
            pytest.skip("no loads")
        load_a = loads[0]
        await _clear_open_memberships(load_a)

        # Trip A planned + attach load, assign, activate A
        r_a = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_a]},
        )
        assert r_a.status_code == 201, r_a.text
        trip_a = int(r_a.json()["id"])

        # activate while Trip planned => blocked
        r_bad = await client.post(
            f"/api/v1/trips/{trip_a}/loads/{load_a}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_bad.status_code == 409, r_bad.text
        assert r_bad.json()["detail"]["code"] == "INVALID_TRIP_STATUS_FOR_ACTIVATE"

        await _assign_trip(client, trip_a)
        r_act_a = await client.post(
            f"/api/v1/trips/{trip_a}/loads/{load_a}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_act_a.status_code == 200, r_act_a.text
        assert await _load_active_trip_id(load_a) == trip_a
        assert r_act_a.json()["status"] == "assigned"  # activation does not start execution

        # Trip B planned while A active
        r_b = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_a]},
        )
        assert r_b.status_code == 201, r_b.text
        trip_b = int(r_b.json()["id"])
        await _assign_trip(client, trip_b)

        # activate B while A active => 409
        r_block = await client.post(
            f"/api/v1/trips/{trip_b}/loads/{load_a}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_block.status_code == 409
        assert r_block.json()["detail"]["code"] == "LOAD_ACTIVE_ON_OTHER_TRIP"

        # complete A
        r_c = await client.post(
            f"/api/v1/trips/{trip_a}/loads/{load_a}/complete",
            headers=AUTH_HEADERS,
        )
        assert r_c.status_code == 200, r_c.text
        row_a = await _membership_row(load_a, trip_a)
        assert row_a is not None
        assert row_a["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED
        assert row_a["completed_at"] is not None
        assert row_a["removed_at"] is None
        assert await _load_active_trip_id(load_a) is None

        row_b = await _membership_row(load_a, trip_b)
        assert row_b is not None
        assert row_b["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_PLANNED

        # activate B after A completed
        r_act_b = await client.post(
            f"/api/v1/trips/{trip_b}/loads/{load_a}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_act_b.status_code == 200, r_act_b.text
        assert await _load_active_trip_id(load_a) == trip_b
        assert r_act_b.json()["status"] == "assigned"

        # in_progress activate path: create trip C planned, assign, start execution, attach planned then activate
        # (use second load if available for isolation)
        # Idempotent activate / complete
        r_act_b2 = await client.post(
            f"/api/v1/trips/{trip_b}/loads/{load_a}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_act_b2.status_code == 200
        assert await _load_active_trip_id(load_a) == trip_b

        r_comp_b = await client.post(
            f"/api/v1/trips/{trip_b}/loads/{load_a}/complete",
            headers=AUTH_HEADERS,
        )
        assert r_comp_b.status_code == 200
        r_comp_b2 = await client.post(
            f"/api/v1/trips/{trip_b}/loads/{load_a}/complete",
            headers=AUTH_HEADERS,
        )
        assert r_comp_b2.status_code == 200
        row_b2 = await _membership_row(load_a, trip_b)
        assert row_b2["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED
        assert row_b2["removed_at"] is None

        # completed -> activate => 409
        r_ca = await client.post(
            f"/api/v1/trips/{trip_b}/loads/{load_a}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_ca.status_code == 409
        assert r_ca.json()["detail"]["code"] == "MEMBERSHIP_ALREADY_COMPLETED"

    async def test_planned_complete_blocked_and_in_progress_activate(
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

        r_pc = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/complete",
            headers=AUTH_HEADERS,
        )
        assert r_pc.status_code == 409
        assert r_pc.json()["detail"]["code"] == "MEMBERSHIP_NOT_ACTIVE"

        await _assign_trip(client, trip_id)
        r_sig = await client.post(
            f"/api/v1/trips/{trip_id}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert r_sig.status_code == 200, r_sig.text
        assert r_sig.json()["status"] == "in_progress"

        r_act = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_act.status_code == 200, r_act.text
        assert r_act.json()["status"] == "in_progress"  # unchanged by activate
        assert await _load_active_trip_id(load_id) == trip_id

    async def test_removed_transitions_blocked_and_cancel_skips_completed(
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
        await _assign_trip(client, trip_id)
        assert (
            await client.post(
                f"/api/v1/trips/{trip_id}/loads/{load_id}/activate",
                headers=AUTH_HEADERS,
            )
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/trips/{trip_id}/loads/{load_id}/complete",
                headers=AUTH_HEADERS,
            )
        ).status_code == 200

        # cancel trip must not rewrite completed membership
        r_cancel = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=AUTH_HEADERS)
        assert r_cancel.status_code == 200, r_cancel.text
        row = await _membership_row(load_id, trip_id)
        assert row["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED
        assert row["completed_at"] is not None
        assert row["removed_at"] is None

        # removed membership: remove open planned on new trip then try activate/complete
        await _clear_open_memberships(load_id)
        r2 = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r2.status_code == 201, r2.text
        trip2 = int(r2.json()["id"])
        assert (
            await client.post(
                f"/api/v1/trips/{trip2}/loads/{load_id}/remove",
                headers=AUTH_HEADERS,
            )
        ).status_code == 200
        r_ra = await client.post(
            f"/api/v1/trips/{trip2}/loads/{load_id}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_ra.status_code == 409
        assert r_ra.json()["detail"]["code"] == "MEMBERSHIP_ALREADY_REMOVED"
        r_rc = await client.post(
            f"/api/v1/trips/{trip2}/loads/{load_id}/complete",
            headers=AUTH_HEADERS,
        )
        assert r_rc.status_code == 409
        assert r_rc.json()["detail"]["code"] == "MEMBERSHIP_ALREADY_REMOVED"

    async def test_multi_load_complete_isolates_and_db_uniques(
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
        await _assign_trip(client, trip_id)
        for lid in (load_a, load_b):
            assert (
                await client.post(
                    f"/api/v1/trips/{trip_id}/loads/{lid}/activate",
                    headers=AUTH_HEADERS,
                )
            ).status_code == 200

        assert (
            await client.post(
                f"/api/v1/trips/{trip_id}/loads/{load_a}/complete",
                headers=AUTH_HEADERS,
            )
        ).status_code == 200
        row_a = await _membership_row(load_a, trip_id)
        row_b = await _membership_row(load_b, trip_id)
        assert row_a["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED
        assert row_b["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        assert row_b["completed_at"] is None
        assert await _load_active_trip_id(load_a) is None
        assert await _load_active_trip_id(load_b) == trip_id

        # DB unique: second open ACTIVE for load_b (still active on trip_id)
        r_empty = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_empty.status_code == 201, r_empty.text
        other_trip = int(r_empty.json()["id"])

        url = _tenant_async_url()
        assert url
        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                tenant_id = (
                    await session.execute(
                        text("SELECT tenant_id FROM loads WHERE id = :lid"),
                        {"lid": load_b},
                    )
                ).scalar()
                with pytest.raises(Exception):
                    await session.execute(
                        text(
                            "INSERT INTO trip_loads "
                            "(tenant_id, trip_id, load_id, status_within_trip, sequence_hint, "
                            "added_at, completed_at, removed_at, created_at, updated_at) "
                            "VALUES (:tid, :trid, :lid, 'active', 0, now(), NULL, NULL, now(), now())"
                        ),
                        {"tid": tenant_id, "trid": other_trip, "lid": load_b},
                    )
                    await session.commit()
                await session.rollback()

                # load_a completed: open planned on other_trip allowed
                await session.execute(
                    text(
                        "INSERT INTO trip_loads "
                        "(tenant_id, trip_id, load_id, status_within_trip, sequence_hint, "
                        "added_at, completed_at, removed_at, created_at, updated_at) "
                        "VALUES (:tid, :trid, :lid, 'planned', 0, now(), NULL, NULL, now(), now())"
                    ),
                    {"tid": tenant_id, "trid": other_trip, "lid": load_a},
                )
                await session.commit()

                r_empty2 = await client.post(
                    "/api/v1/trips",
                    headers=AUTH_HEADERS,
                    json={"status": "planned", "job_type": "freight_load", "load_ids": []},
                )
                assert r_empty2.status_code == 201, r_empty2.text
                other_trip2 = int(r_empty2.json()["id"])

                with pytest.raises(Exception):
                    await session.execute(
                        text(
                            "INSERT INTO trip_loads "
                            "(tenant_id, trip_id, load_id, status_within_trip, sequence_hint, "
                            "added_at, completed_at, removed_at, created_at, updated_at) "
                            "VALUES (:tid, :trid, :lid, 'planned', 0, now(), NULL, NULL, now(), now())"
                        ),
                        {"tid": tenant_id, "trid": other_trip2, "lid": load_a},
                    )
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    async def test_is_open_predicate_logic(self):
        def is_open(m: dict) -> bool:
            st = (m.get("status_within_trip") or "").lower()
            return (
                st in ("planned", "active")
                and m.get("completed_at") is None
                and m.get("removed_at") is None
            )

        assert is_open({"status_within_trip": "active", "completed_at": None, "removed_at": None})
        assert is_open({"status_within_trip": "planned", "completed_at": None, "removed_at": None})
        assert not is_open(
            {"status_within_trip": "completed", "completed_at": "2026-01-01", "removed_at": None}
        )
        assert not is_open(
            {"status_within_trip": "removed", "completed_at": None, "removed_at": "2026-01-01"}
        )
        assert not is_open(
            {"status_within_trip": "active", "completed_at": None, "removed_at": "2026-01-01"}
        )

    async def test_activate_assigned_requires_complete_assignment(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        ids = await _first_driver_truck_trailer(client)
        if ids is None:
            pytest.skip("no driver/truck/trailer")
        d_id, t_id, r_id = ids
        load_id = loads[0]
        await _clear_open_memberships(load_id)

        async def _create_planned() -> int:
            r = await client.post(
                "/api/v1/trips",
                headers=AUTH_HEADERS,
                json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
            )
            assert r.status_code == 201, r.text
            return int(r.json()["id"])

        # A. full assignment -> activate succeeds
        trip_ok = await _create_planned()
        await _assign_trip(client, trip_ok)
        r_ok = await client.post(
            f"/api/v1/trips/{trip_ok}/loads/{load_id}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_ok.status_code == 200, r_ok.text
        # F. idempotent activate
        r_idem = await client.post(
            f"/api/v1/trips/{trip_ok}/loads/{load_id}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_idem.status_code == 200
        assert await _load_active_trip_id(load_id) == trip_ok
        await _clear_open_memberships(load_id)

        # B/C/D. hollow assigned via POST /trips status=assigned missing one resource
        for missing, body in (
            (
                "driver",
                {"status": "assigned", "job_type": "freight_load", "load_ids": [load_id],
                 "driver_id": None, "truck_id": t_id, "trailer_id": r_id},
            ),
            (
                "truck",
                {"status": "assigned", "job_type": "freight_load", "load_ids": [load_id],
                 "driver_id": d_id, "truck_id": None, "trailer_id": r_id},
            ),
            (
                "trailer",
                {"status": "assigned", "job_type": "freight_load", "load_ids": [load_id],
                 "driver_id": d_id, "truck_id": t_id, "trailer_id": None},
            ),
        ):
            await _clear_open_memberships(load_id)
            r_create = await client.post("/api/v1/trips", headers=AUTH_HEADERS, json=body)
            assert r_create.status_code == 201, f"{missing}: {r_create.text}"
            trip_id = int(r_create.json()["id"])
            assert r_create.json()["status"] == "assigned"
            r_act = await client.post(
                f"/api/v1/trips/{trip_id}/loads/{load_id}/activate",
                headers=AUTH_HEADERS,
            )
            assert r_act.status_code == 409, f"{missing}: {r_act.text}"
            assert r_act.json()["detail"]["code"] == "TRIP_ASSIGNMENT_INCOMPLETE"
            assert "driver" in r_act.json()["detail"]["detail"].lower()

        # E. in_progress allows activate without rechecking (after clear + new trip)
        await _clear_open_memberships(load_id)
        trip_ip = await _create_planned()
        await _assign_trip(client, trip_ip)
        r_sig = await client.post(
            f"/api/v1/trips/{trip_ip}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        assert r_sig.status_code == 200, r_sig.text
        assert r_sig.json()["status"] == "in_progress"
        r_act_ip = await client.post(
            f"/api/v1/trips/{trip_ip}/loads/{load_id}/activate",
            headers=AUTH_HEADERS,
        )
        assert r_act_ip.status_code == 200, r_act_ip.text
        assert r_act_ip.json()["status"] == "in_progress"
        assert await _load_active_trip_id(load_id) == trip_ip
