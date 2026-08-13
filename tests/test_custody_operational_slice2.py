"""Custody Slice 2 — accept-custody / yard-handoff / take-custody operational transitions."""

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

from app.constants.custody import (
    CUSTODY_EVENT_TRIP_ACCEPT,
    CUSTODY_EVENT_TRIP_TAKEOVER,
    CUSTODY_EVENT_YARD_HANDOFF,
    CUSTODY_OWNER_TERMINAL,
    CUSTODY_OWNER_TRIP,
    CUSTODY_OWNER_UNKNOWN,
    CUSTODY_PLACEMENT_ON_TRAILER,
    CUSTODY_PLACEMENT_STAGED,
)
from app.constants.trip_dispatch import (
    TRIP_LOAD_STATUS_WITHIN_ACTIVE,
    TRIP_LOAD_STATUS_WITHIN_COMPLETED,
    TRIP_LOAD_STATUS_WITHIN_PLANNED,
)
from app.main import app
from tests.support.custody_http import (
    accept_custody,
    ensure_active_terminal,
    reset_custody_to_unknown,
    take_custody,
    yard_handoff,
)
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (
    os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
)
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
    prefix = f"C{uuid.uuid4().hex[:7].upper()}"
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
    lr = await client.get("/api/v1/loads?page=1&size=40", headers=AUTH_HEADERS)
    if lr.status_code != 200:
        return []
    items = lr.json().get("items") or []
    return [int(x["id"]) for x in items[:n]]


async def _first_driver_truck_trailer(client: AsyncClient) -> tuple[int, int, int] | None:
    dr = await client.get("/api/v1/drivers?limit=5", headers=AUTH_HEADERS)
    tr = await client.get("/api/v1/trucks?page=1&size=5", headers=AUTH_HEADERS)
    rr = await client.get("/api/v1/trailers?page=1&size=10", headers=AUTH_HEADERS)
    if dr.status_code != 200 or tr.status_code != 200 or rr.status_code != 200:
        return None
    dlist = dr.json()
    tlist = tr.json().get("items") or []
    rlist = rr.json().get("items") or []
    if not dlist or not tlist or not rlist:
        return None
    return int(dlist[0]["id"]), int(tlist[0]["id"]), int(rlist[0]["id"])


async def _two_trailers(client: AsyncClient) -> tuple[int, int] | None:
    rr = await client.get("/api/v1/trailers?page=1&size=10", headers=AUTH_HEADERS)
    if rr.status_code != 200:
        return None
    rlist = rr.json().get("items") or []
    if len(rlist) < 2:
        return None
    return int(rlist[0]["id"]), int(rlist[1]["id"])


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


async def _load_row(load_id: int) -> dict:
    engine, Session = await _session()
    try:
        async with Session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, active_trip_id, custody_owner, custody_trip_id, "
                        "custody_terminal_id, custody_placement, custody_trailer_id, "
                        "last_custody_event_id FROM loads WHERE id = :lid"
                    ),
                    {"lid": load_id},
                )
            ).mappings().one()
            return dict(row)
    finally:
        await engine.dispose()


async def _membership(load_id: int, trip_id: int) -> dict | None:
    engine, Session = await _session()
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


async def _event_count(load_id: int, event_type: str) -> int:
    engine, Session = await _session()
    try:
        async with Session() as session:
            return int(
                (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM load_custody_events "
                            "WHERE load_id = :lid AND event_type = :et"
                        ),
                        {"lid": load_id, "et": event_type},
                    )
                ).scalar()
                or 0
            )
    finally:
        await engine.dispose()


async def _create_assigned_trip(
    client: AsyncClient,
    load_ids: list[int],
    *,
    trailer_id: int | None = None,
    clear_open: bool = False,
) -> tuple[int, int, dict]:
    """Return (trip_id, trailer_id, trip_json) for an assigned trip with memberships planned."""
    ids = await _first_driver_truck_trailer(client)
    if ids is None:
        pytest.skip("no driver/truck/trailer")
    d_id, t_id, r_id = ids
    if trailer_id is not None:
        r_id = trailer_id
    if clear_open:
        for lid in load_ids:
            await _clear_open_memberships(lid)
    created = await client.post(
        "/api/v1/trips",
        headers=AUTH_HEADERS,
        json={"status": "planned", "job_type": "freight_load", "load_ids": load_ids},
    )
    assert created.status_code == 201, created.text
    trip_id = int(created.json()["id"])
    assigned = await client.put(
        f"/api/v1/trips/{trip_id}/assignment",
        headers=AUTH_HEADERS,
        json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
    )
    assert assigned.status_code == 200, assigned.text
    return trip_id, r_id, assigned.json()


@pytest.mark.skipif(REQUIRES_DB or REQUIRES_TENANT_DB or _PLACEHOLDER_PLATFORM_DB, reason="integration")
@pytest.mark.asyncio
class TestCustodyOperationalSlice2:
    async def test_accept_custody_happy_path_and_invariants(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        before = await _load_row(load_id)
        trip_id, trailer_id, trip_body = await _create_assigned_trip(client, [load_id])
        trip_status_before = trip_body["status"]
        load_status_before = before["status"]

        r = await accept_custody(client, AUTH_HEADERS, trip_id, load_id)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["membership_status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        assert body["active_trip_id"] == trip_id
        assert body["trip_status"] == trip_status_before
        assert body["load_status"] == load_status_before
        assert body["snapshot"]["custody_owner"] == CUSTODY_OWNER_TRIP
        assert body["snapshot"]["custody_trip_id"] == trip_id
        assert body["snapshot"]["custody_placement"] == CUSTODY_PLACEMENT_ON_TRAILER
        assert body["snapshot"]["custody_trailer_id"] == trailer_id
        assert body["event"]["event_type"] == CUSTODY_EVENT_TRIP_ACCEPT
        assert body["replayed"] is False

        row = await _load_row(load_id)
        assert row["active_trip_id"] == trip_id
        assert row["custody_owner"] == CUSTODY_OWNER_TRIP
        assert row["status"] == load_status_before
        mem = await _membership(load_id, trip_id)
        assert mem and mem["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        assert await _event_count(load_id, CUSTODY_EVENT_TRIP_ACCEPT) >= 1

        detail = await client.get(f"/api/v1/trips/{trip_id}", headers=AUTH_HEADERS)
        assert detail.status_code == 200
        assert detail.json()["status"] == trip_status_before

    async def test_accept_missing_trailer_rejected(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        trip_id, _trailer, _ = await _create_assigned_trip(client, [load_id])
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
        r = await accept_custody(client, AUTH_HEADERS, trip_id, load_id)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] in (
            "TRIP_TRAILER_REQUIRED",
            "TRIP_ASSIGNMENT_INCOMPLETE",
        )

    async def test_accept_wrong_custody_and_other_active(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        trip_a, _, _ = await _create_assigned_trip(client, [load_id])
        assert (
            await accept_custody(client, AUTH_HEADERS, trip_a, load_id)
        ).status_code == 200

        trip_b, _, _ = await _create_assigned_trip(client, [load_id])
        # other active blocks before custody-state check
        r_block = await accept_custody(
            client, AUTH_HEADERS, trip_b, load_id, reset_unknown=False
        )
        assert r_block.status_code == 409
        assert r_block.json()["detail"]["code"] == "LOAD_ACTIVE_ON_OTHER_TRIP"

        # Force terminal custody without completing A (invalid for accept): complete via handoff first
        terminal_id = await ensure_active_terminal(client, AUTH_HEADERS)
        assert (
            await yard_handoff(
                client, AUTH_HEADERS, trip_a, load_id, terminal_id=terminal_id, placement="staged"
            )
        ).status_code == 200
        # Now planned on B + terminal custody → accept must reject (use take instead)
        r_wrong = await accept_custody(
            client, AUTH_HEADERS, trip_b, load_id, reset_unknown=False
        )
        assert r_wrong.status_code == 409
        assert r_wrong.json()["detail"]["code"] == "INVALID_CUSTODY_STATE"

    async def test_accept_idempotent_no_duplicate_event(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        trip_id, _, _ = await _create_assigned_trip(client, [load_id])
        key = f"accept-{uuid.uuid4().hex}"
        r1 = await accept_custody(
            client, AUTH_HEADERS, trip_id, load_id, body={"idempotency_key": key}
        )
        assert r1.status_code == 200, r1.text
        n1 = await _event_count(load_id, CUSTODY_EVENT_TRIP_ACCEPT)
        r2 = await accept_custody(
            client,
            AUTH_HEADERS,
            trip_id,
            load_id,
            reset_unknown=False,
            body={"idempotency_key": key},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["replayed"] is True
        assert await _event_count(load_id, CUSTODY_EVENT_TRIP_ACCEPT) == n1

    async def test_yard_handoff_happy_on_trailer_and_staged(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 2)
        if len(loads) < 2:
            pytest.skip("need 2 loads")
        load_a, load_b = loads[0], loads[1]
        await _clear_open_memberships(load_a)
        await _clear_open_memberships(load_b)
        trip_id, trailer_id, trip_body = await _create_assigned_trip(client, [load_a, load_b])
        trip_status = trip_body["status"]
        terminal_id = await ensure_active_terminal(client, AUTH_HEADERS)

        assert (await accept_custody(client, AUTH_HEADERS, trip_id, load_a)).status_code == 200
        assert (await accept_custody(client, AUTH_HEADERS, trip_id, load_b)).status_code == 200

        # outbound planned must stay planned after handoff A
        outbound, _, _ = await _create_assigned_trip(client, [load_a])

        r_on = await yard_handoff(
            client,
            AUTH_HEADERS,
            trip_id,
            load_a,
            terminal_id=terminal_id,
            placement="on_trailer",
        )
        assert r_on.status_code == 200, r_on.text
        assert r_on.json()["snapshot"]["custody_owner"] == CUSTODY_OWNER_TERMINAL
        assert r_on.json()["snapshot"]["custody_placement"] == CUSTODY_PLACEMENT_ON_TRAILER
        assert r_on.json()["snapshot"]["custody_trailer_id"] == trailer_id
        assert r_on.json()["membership_status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED
        assert r_on.json()["active_trip_id"] is None
        assert r_on.json()["trip_status"] == trip_status
        assert r_on.json()["event"]["event_type"] == CUSTODY_EVENT_YARD_HANDOFF

        mem_b = await _membership(load_b, trip_id)
        assert mem_b and mem_b["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        mem_out = await _membership(load_a, outbound)
        assert mem_out and mem_out["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_PLANNED

        r_st = await yard_handoff(
            client,
            AUTH_HEADERS,
            trip_id,
            load_b,
            terminal_id=terminal_id,
            placement="staged",
        )
        assert r_st.status_code == 200, r_st.text
        assert r_st.json()["snapshot"]["custody_placement"] == CUSTODY_PLACEMENT_STAGED
        assert r_st.json()["snapshot"]["custody_trailer_id"] is None
        assert (await _load_row(load_b))["active_trip_id"] is None

    async def test_yard_handoff_rejects_and_idempotency(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        trip_id, trailer_id, _ = await _create_assigned_trip(client, [load_id])
        terminal_id = await ensure_active_terminal(client, AUTH_HEADERS)
        assert (await accept_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200

        r404 = await yard_handoff(
            client, AUTH_HEADERS, trip_id, load_id, terminal_id=9_999_999, placement="staged"
        )
        assert r404.status_code == 404
        assert r404.json()["detail"]["code"] == "TERMINAL_NOT_FOUND"

        inactive = await client.post(
            "/api/v1/terminals",
            headers=AUTH_HEADERS,
            json={"name": f"Dead-{uuid.uuid4().hex[:6]}", "city": "X"},
        )
        assert inactive.status_code == 201
        dead_id = int(inactive.json()["id"])
        patched = await client.patch(
            f"/api/v1/terminals/{dead_id}",
            headers=AUTH_HEADERS,
            json={"is_active": False},
        )
        assert patched.status_code == 200, patched.text
        r_in = await yard_handoff(
            client, AUTH_HEADERS, trip_id, load_id, terminal_id=dead_id, placement="staged"
        )
        assert r_in.status_code == 409
        assert r_in.json()["detail"]["code"] == "TERMINAL_INACTIVE"

        # trailer mismatch on_trailer
        other = await _two_trailers(client)
        if other and other[1] != trailer_id:
            r_mm = await yard_handoff(
                client,
                AUTH_HEADERS,
                trip_id,
                load_id,
                terminal_id=terminal_id,
                placement="on_trailer",
                body={"trailer_id": other[1]},
            )
            assert r_mm.status_code == 409
            assert r_mm.json()["detail"]["code"] == "TRAILER_MISMATCH"

        # custody mismatch: reset snapshot while membership still active
        await reset_custody_to_unknown(load_id)
        r_mis = await yard_handoff(
            client, AUTH_HEADERS, trip_id, load_id, terminal_id=terminal_id, placement="staged"
        )
        assert r_mis.status_code == 409
        assert r_mis.json()["detail"]["code"] == "CUSTODY_SNAPSHOT_MISMATCH"

        # Restore trip custody snapshot (membership still ACTIVE) then idempotent handoff
        engine, Session = await _session()
        try:
            async with Session() as session:
                await session.execute(
                    text(
                        "UPDATE loads SET custody_owner = 'trip', custody_trip_id = :tid, "
                        "custody_terminal_id = NULL, custody_placement = 'on_trailer', "
                        "custody_trailer_id = :rid, active_trip_id = :tid WHERE id = :lid"
                    ),
                    {"tid": trip_id, "rid": trailer_id, "lid": load_id},
                )
                await session.commit()
        finally:
            await engine.dispose()
        key = f"hand-{uuid.uuid4().hex}"
        r1 = await yard_handoff(
            client,
            AUTH_HEADERS,
            trip_id,
            load_id,
            terminal_id=terminal_id,
            placement="staged",
            body={"idempotency_key": key},
        )
        assert r1.status_code == 200, r1.text
        n1 = await _event_count(load_id, CUSTODY_EVENT_YARD_HANDOFF)
        r2 = await yard_handoff(
            client,
            AUTH_HEADERS,
            trip_id,
            load_id,
            terminal_id=terminal_id,
            placement="staged",
            body={"idempotency_key": key},
        )
        assert r2.status_code == 200
        assert r2.json()["replayed"] is True
        assert await _event_count(load_id, CUSTODY_EVENT_YARD_HANDOFF) == n1

    async def test_take_custody_staged_and_trailer_rules(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        trailers = await _two_trailers(client)
        if not trailers:
            pytest.skip("need 2 trailers")
        tr_a, tr_b = trailers
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        terminal_id = await ensure_active_terminal(client, AUTH_HEADERS)

        trip_in, _, _ = await _create_assigned_trip(client, [load_id], trailer_id=tr_a)
        assert (await accept_custody(client, AUTH_HEADERS, trip_in, load_id)).status_code == 200
        assert (
            await yard_handoff(
                client,
                AUTH_HEADERS,
                trip_in,
                load_id,
                terminal_id=terminal_id,
                placement="staged",
            )
        ).status_code == 200

        trip_out, out_trailer, out_body = await _create_assigned_trip(
            client, [load_id], trailer_id=tr_b
        )
        load_status = (await _load_row(load_id))["status"]
        r = await take_custody(client, AUTH_HEADERS, trip_out, load_id)
        assert r.status_code == 200, r.text
        assert r.json()["snapshot"]["custody_owner"] == CUSTODY_OWNER_TRIP
        assert r.json()["snapshot"]["custody_trip_id"] == trip_out
        assert r.json()["snapshot"]["custody_trailer_id"] == out_trailer
        assert r.json()["membership_status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        assert r.json()["active_trip_id"] == trip_out
        assert r.json()["trip_status"] == out_body["status"]
        assert r.json()["load_status"] == load_status
        assert r.json()["event"]["event_type"] == CUSTODY_EVENT_TRIP_TAKEOVER

        # handoff on_trailer then same trailer take ok; different trailer blocked
        assert (
            await yard_handoff(
                client,
                AUTH_HEADERS,
                trip_out,
                load_id,
                terminal_id=terminal_id,
                placement="on_trailer",
            )
        ).status_code == 200

        trip_same, _, _ = await _create_assigned_trip(client, [load_id], trailer_id=out_trailer)
        assert (await take_custody(client, AUTH_HEADERS, trip_same, load_id)).status_code == 200
        assert (
            await yard_handoff(
                client,
                AUTH_HEADERS,
                trip_same,
                load_id,
                terminal_id=terminal_id,
                placement="on_trailer",
            )
        ).status_code == 200

        trip_diff, _, _ = await _create_assigned_trip(client, [load_id], trailer_id=tr_a)
        r_diff = await take_custody(client, AUTH_HEADERS, trip_diff, load_id)
        assert r_diff.status_code == 409
        assert r_diff.json()["detail"]["code"] == "TRAILER_MISMATCH"

    async def test_take_custody_idempotent_and_other_active_blocked(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        terminal_id = await ensure_active_terminal(client, AUTH_HEADERS)
        trip_a, _, _ = await _create_assigned_trip(client, [load_id])
        assert (await accept_custody(client, AUTH_HEADERS, trip_a, load_id)).status_code == 200
        assert (
            await yard_handoff(
                client, AUTH_HEADERS, trip_a, load_id, terminal_id=terminal_id, placement="staged"
            )
        ).status_code == 200

        trip_b, _, _ = await _create_assigned_trip(client, [load_id])
        key = f"take-{uuid.uuid4().hex}"
        r1 = await take_custody(
            client, AUTH_HEADERS, trip_b, load_id, body={"idempotency_key": key}
        )
        assert r1.status_code == 200, r1.text
        n1 = await _event_count(load_id, CUSTODY_EVENT_TRIP_TAKEOVER)
        r2 = await take_custody(
            client, AUTH_HEADERS, trip_b, load_id, body={"idempotency_key": key}
        )
        assert r2.status_code == 200
        assert r2.json()["replayed"] is True
        assert await _event_count(load_id, CUSTODY_EVENT_TRIP_TAKEOVER) == n1

        trip_c, _, _ = await _create_assigned_trip(client, [load_id])
        r_block = await take_custody(client, AUTH_HEADERS, trip_c, load_id)
        assert r_block.status_code == 409
        assert r_block.json()["detail"]["code"] == "LOAD_ACTIVE_ON_OTHER_TRIP"

    async def test_bare_activate_complete_closed(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        trip_id, _, _ = await _create_assigned_trip(client, [load_id])
        act = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/activate", headers=AUTH_HEADERS
        )
        assert act.status_code == 409
        assert act.json()["detail"]["code"] == "MEMBERSHIP_TRANSITION_REQUIRES_CUSTODY"

        assert (await accept_custody(client, AUTH_HEADERS, trip_id, load_id)).status_code == 200
        done = await client.post(
            f"/api/v1/trips/{trip_id}/loads/{load_id}/complete", headers=AUTH_HEADERS
        )
        assert done.status_code == 409
        assert done.json()["detail"]["code"] == "MEMBERSHIP_TRANSITION_REQUIRES_CUSTODY"

    async def test_acme_flow(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 1)
        if not loads:
            pytest.skip("no loads")
        load_id = loads[0]
        await _clear_open_memberships(load_id)
        terminal_id = await ensure_active_terminal(client, AUTH_HEADERS, name=f"ACME-{uuid.uuid4().hex[:6]}")

        trip_a, _, _ = await _create_assigned_trip(client, [load_id])
        assert (await accept_custody(client, AUTH_HEADERS, trip_a, load_id)).status_code == 200
        assert (await _membership(load_id, trip_a))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        trip_b, _, _ = await _create_assigned_trip(client, [load_id])
        assert (await _membership(load_id, trip_b))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_PLANNED
        assert (await _load_row(load_id))["active_trip_id"] == trip_a

        assert (
            await yard_handoff(
                client, AUTH_HEADERS, trip_a, load_id, terminal_id=terminal_id, placement="staged"
            )
        ).status_code == 200
        assert (await _membership(load_id, trip_a))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED
        assert (await _membership(load_id, trip_b))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_PLANNED
        assert (await _load_row(load_id))["custody_owner"] == CUSTODY_OWNER_TERMINAL
        assert (await _load_row(load_id))["active_trip_id"] is None

        # Trip A complete requires in_progress + no open memberships — start then close
        sig = await client.post(
            f"/api/v1/trips/{trip_a}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        if sig.status_code == 200:
            done = await client.post(f"/api/v1/trips/{trip_a}/complete", headers=AUTH_HEADERS)
            assert done.status_code == 200, done.text

        assert (await take_custody(client, AUTH_HEADERS, trip_b, load_id)).status_code == 200
        assert (await _membership(load_id, trip_b))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        assert (await _load_row(load_id))["active_trip_id"] == trip_b
        assert (await _membership(load_id, trip_a))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED

    async def test_boston_albany_branching(
        self, client: AsyncClient, locked_prefix: str, override_auth_tenant
    ):
        loads = await _pick_load_ids(client, 2)
        if len(loads) < 2:
            pytest.skip("need 2 loads")
        load_a, load_b = loads[0], loads[1]
        await _clear_open_memberships(load_a)
        await _clear_open_memberships(load_b)
        terminal_id = await ensure_active_terminal(
            client, AUTH_HEADERS, name=f"Boston-{uuid.uuid4().hex[:6]}"
        )

        trip_in, _, _ = await _create_assigned_trip(client, [load_a, load_b])
        assert (await accept_custody(client, AUTH_HEADERS, trip_in, load_a)).status_code == 200
        assert (await accept_custody(client, AUTH_HEADERS, trip_in, load_b)).status_code == 200

        assert (
            await yard_handoff(
                client, AUTH_HEADERS, trip_in, load_a, terminal_id=terminal_id, placement="staged"
            )
        ).status_code == 200
        assert (await _membership(load_a, trip_in))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_COMPLETED
        assert (await _membership(load_b, trip_in))["status_within_trip"] == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        assert (await _load_row(load_a))["custody_owner"] == CUSTODY_OWNER_TERMINAL
        assert (await _load_row(load_b))["custody_owner"] == CUSTODY_OWNER_TRIP

        assert (
            await yard_handoff(
                client, AUTH_HEADERS, trip_in, load_b, terminal_id=terminal_id, placement="staged"
            )
        ).status_code == 200

        sig = await client.post(
            f"/api/v1/trips/{trip_in}/execution-signal",
            headers=AUTH_HEADERS,
            json={"source": "dispatcher_manual"},
        )
        if sig.status_code == 200:
            assert (
                await client.post(f"/api/v1/trips/{trip_in}/complete", headers=AUTH_HEADERS)
            ).status_code == 200

        trip_out_a, _, _ = await _create_assigned_trip(client, [load_a])
        trip_out_b, _, _ = await _create_assigned_trip(client, [load_b])

        assert (await take_custody(client, AUTH_HEADERS, trip_out_a, load_a)).status_code == 200
        assert (await _load_row(load_b))["custody_owner"] == CUSTODY_OWNER_TERMINAL
        assert (await _load_row(load_a))["active_trip_id"] == trip_out_a

        assert (await take_custody(client, AUTH_HEADERS, trip_out_b, load_b)).status_code == 200
        assert (await _load_row(load_a))["active_trip_id"] == trip_out_a
        assert (await _load_row(load_b))["active_trip_id"] == trip_out_b
        assert (await _load_row(load_a))["custody_owner"] == CUSTODY_OWNER_TRIP
        assert (await _load_row(load_b))["custody_owner"] == CUSTODY_OWNER_TRIP
