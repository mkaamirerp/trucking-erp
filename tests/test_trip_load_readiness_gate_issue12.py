"""Issue I12 — planned TripLoad membership requires Load.status = ready."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.trip_dispatch import (
    LOAD_NOT_READY_FOR_TRIP,
    TRIP_LOAD_STATUS_WITHIN_ACTIVE,
    TRIP_LOAD_STATUS_WITHIN_PLANNED,
)
from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError, integration_tenant_db_name
from app.main import app
from app.services.trips import _insert_trip_load_row
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import (
    AUTH_HEADERS,
    assert_mutating_integration_allowed,
    database_name_from_url,
    require_integration_tenant_database_url,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

_VALID_STOPS = [
    {"stop_type": "PICKUP", "sequence": 0, "city": "Austin", "state_or_province": "TX"},
    {"stop_type": "DROP", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
]


def _detail_code(payload: dict) -> str | None:
    d = payload.get("detail")
    return d.get("code") if isinstance(d, dict) else None


def _integration_db_configured() -> bool:
    try:
        require_integration_tenant_database_url(context="issue12_readiness_gate_precheck")
        return True
    except IntegrationIsolationError:
        return False


_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
SKIP_ISSUE12_HTTP = _PLACEHOLDER_PLATFORM_DB or not _integration_db_configured()


async def _cleanup_load_rows(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context="issue12_cleanup_load")
    await db.execute(
        text(
            "delete from trip_loads where tenant_id=:t and load_id=:i"
        ),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text(
            "delete from audit_events where tenant_id=:t and entity_type='load' and entity_id=:e"
        ),
        {"t": tenant_id, "e": str(load_id)},
    )
    await db.execute(
        text("delete from load_stops where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from load_notes where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.commit()


async def _cleanup_trip_rows(db: AsyncSession, tenant_id: int, trip_id: int) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context="issue12_cleanup_trip")
    await db.execute(
        text("delete from trip_loads where tenant_id=:t and trip_id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    await db.execute(
        text("delete from trips where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    await db.commit()


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
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
def issue12_integration_gate():
    try:
        tenant_url = require_integration_tenant_database_url(context="issue12_readiness_gate")
    except IntegrationIsolationError as exc:
        pytest.skip(f"Issue I12 HTTP tests require isolated tenant DB: {exc}")
    db_name = database_name_from_url(tenant_url)
    expected = integration_tenant_db_name()
    if db_name != expected:
        pytest.skip(
            f"Issue I12 HTTP tests require database {expected!r}, got {db_name!r}."
        )
    return {"tenant_database_url": tenant_url, "tenant_db_name": db_name}


@pytest.fixture
async def issue12_http(client, override_auth_tenant, issue12_integration_gate):
    tenant_id = await platform_tenant_id_for_slug()
    await assert_mutating_integration_allowed(
        tenant_id=tenant_id,
        host=AUTH_HEADERS["host"],
        context="issue12_readiness_gate",
    )
    gate = issue12_integration_gate
    created_load_ids: list[int] = []
    created_trip_ids: list[int] = []

    async def new_draft(tag: str, **extra) -> dict:
        r = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"{tag}-{uuid.uuid4().hex[:8]}", **extra},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        created_load_ids.append(int(body["id"]))
        return body

    async def mark_ready(load_body: dict) -> dict:
        cv = load_body["concurrency_version"]
        r = await client.post(
            f"/api/v1/loads/{load_body['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": cv},
        )
        assert r.status_code == 200, r.text
        return r.json()

    async def new_ready(tag: str) -> dict:
        draft = await new_draft(
            tag,
            broker_name_snapshot="Broker",
            broker_load_reference="REF-I12",
            stops=_VALID_STOPS,
        )
        return await mark_ready(draft)

    ctx = SimpleNamespace(
        client=client,
        tenant_id=tenant_id,
        new_draft=new_draft,
        new_ready=new_ready,
        mark_ready=mark_ready,
        tenant_url=gate["tenant_database_url"],
        track_trip=lambda tid: created_trip_ids.append(int(tid)),
    )
    try:
        yield ctx
    finally:
        if created_load_ids or created_trip_ids:
            engine = create_async_engine(
                to_async_pg_url(gate["tenant_database_url"]), pool_pre_ping=True
            )
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            try:
                async with Session() as db:
                    for trip_id in reversed(created_trip_ids):
                        await _cleanup_trip_rows(db, tenant_id, trip_id)
                    for load_id in reversed(created_load_ids):
                        await _cleanup_load_rows(db, tenant_id, load_id)
            finally:
                await engine.dispose()


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


@pytest.mark.skipif(SKIP_ISSUE12_HTTP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
class TestTripLoadReadinessGateIssue12:
    async def test_a_draft_load_rejected_409(self, issue12_http, locked_prefix: str) -> None:
        draft = await issue12_http.new_draft(
            "I12-DRAFT",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-1",
            stops=_VALID_STOPS,
        )
        r = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [draft["id"]]},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LOAD_NOT_READY_FOR_TRIP

    async def test_b_stable_error_code(self, issue12_http, locked_prefix: str) -> None:
        draft = await issue12_http.new_draft("I12-CODE")
        r = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [draft["id"]]},
        )
        assert r.status_code == 409
        body = r.json()
        assert body.get("detail", {}).get("code") == LOAD_NOT_READY_FOR_TRIP

    async def test_c_ready_load_accepted(self, issue12_http, locked_prefix: str) -> None:
        ready = await issue12_http.new_ready("I12-READY")
        r = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [ready["id"]]},
        )
        assert r.status_code == 201, r.text
        issue12_http.track_trip(int(r.json()["id"]))

    async def test_d_cancelled_load_rejected(self, issue12_http, locked_prefix: str) -> None:
        ready = await issue12_http.new_ready("I12-CANCEL")
        load_id = int(ready["id"])
        engine = create_async_engine(to_async_pg_url(issue12_http.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                await db.execute(
                    text("update loads set status = 'cancelled' where id = :i and tenant_id = :t"),
                    {"i": load_id, "t": issue12_http.tenant_id},
                )
                await db.commit()
        finally:
            await engine.dispose()

        r = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LOAD_NOT_READY_FOR_TRIP

    async def test_e_legacy_status_rejected(self, issue12_http, locked_prefix: str) -> None:
        ready = await issue12_http.new_ready("I12-LEGACY")
        load_id = int(ready["id"])
        engine = create_async_engine(to_async_pg_url(issue12_http.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                await db.execute(
                    text("update loads set status = 'dispatched' where id = :i and tenant_id = :t"),
                    {"i": load_id, "t": issue12_http.tenant_id},
                )
                await db.commit()
        finally:
            await engine.dispose()

        r = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LOAD_NOT_READY_FOR_TRIP

    async def test_f_wrong_tenant_load_404(self, issue12_http, locked_prefix: str) -> None:
        ready = await issue12_http.new_ready("I12-404")
        r_trip = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_trip.status_code == 201, r_trip.text
        trip_id = int(r_trip.json()["id"])
        issue12_http.track_trip(trip_id)

        engine = create_async_engine(to_async_pg_url(issue12_http.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                other_tenant = issue12_http.tenant_id + 99_999
                with pytest.raises(HTTPException) as ei:
                    await _insert_trip_load_row(
                        session,
                        other_tenant,
                        trip_id,
                        int(ready["id"]),
                        sequence_hint=None,
                    )
                assert ei.value.status_code == 404
                with pytest.raises(HTTPException) as ej:
                    await _insert_trip_load_row(
                        session,
                        issue12_http.tenant_id,
                        trip_id,
                        999_999_999,
                        sequence_hint=None,
                    )
                assert ej.value.status_code == 404
                await session.rollback()
        finally:
            await engine.dispose()

    async def test_g_create_planned_trip_respects_gate(self, issue12_http, locked_prefix: str) -> None:
        draft = await issue12_http.new_draft("I12-G")
        r_bad = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [draft["id"]]},
        )
        assert r_bad.status_code == 409
        ready = await issue12_http.new_ready("I12-G-OK")
        r_ok = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [ready["id"]]},
        )
        assert r_ok.status_code == 201, r_ok.text
        issue12_http.track_trip(int(r_ok.json()["id"]))

    async def test_h_add_load_to_trip_respects_gate(self, issue12_http, locked_prefix: str) -> None:
        r_trip = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_trip.status_code == 201, r_trip.text
        trip_id = int(r_trip.json()["id"])
        issue12_http.track_trip(trip_id)

        draft = await issue12_http.new_draft("I12-H")
        r_bad = await issue12_http.client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": draft["id"]},
        )
        assert r_bad.status_code == 409
        assert _detail_code(r_bad.json()) == LOAD_NOT_READY_FOR_TRIP

        ready = await issue12_http.new_ready("I12-H-OK")
        r_ok = await issue12_http.client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": ready["id"]},
        )
        assert r_ok.status_code == 200, r_ok.text

    async def test_i_membership_history_unchanged_on_reject(
        self, issue12_http, locked_prefix: str
    ) -> None:
        ready = await issue12_http.new_ready("I12-I")
        load_id = int(ready["id"])
        r_ok = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": [load_id]},
        )
        assert r_ok.status_code == 201, r_ok.text
        trip_id = int(r_ok.json()["id"])
        issue12_http.track_trip(trip_id)

        engine = create_async_engine(to_async_pg_url(issue12_http.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                before = int(
                    (
                        await db.execute(
                            text(
                                "select count(*) from trip_loads where tenant_id=:t and load_id=:l"
                            ),
                            {"t": issue12_http.tenant_id, "l": load_id},
                        )
                    ).scalar()
                    or 0
                )
        finally:
            await engine.dispose()

        draft = await issue12_http.new_draft("I12-I-DRAFT")
        r_bad = await issue12_http.client.post(
            f"/api/v1/trips/{trip_id}/loads",
            headers=AUTH_HEADERS,
            json={"load_id": draft["id"]},
        )
        assert r_bad.status_code == 409

        engine = create_async_engine(to_async_pg_url(issue12_http.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                after = int(
                    (
                        await db.execute(
                            text(
                                "select count(*) from trip_loads where tenant_id=:t and load_id=:l"
                            ),
                            {"t": issue12_http.tenant_id, "l": load_id},
                        )
                    ).scalar()
                    or 0
                )
        finally:
            await engine.dispose()
        assert before == after == 1

    async def test_j_active_path_unchanged_for_draft(
        self, issue12_http, locked_prefix: str
    ) -> None:
        draft = await issue12_http.new_draft(
            "I12-J",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-J",
            stops=_VALID_STOPS,
        )
        load_id = int(draft["id"])

        r_trip = await issue12_http.client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r_trip.status_code == 201, r_trip.text
        trip_id = int(r_trip.json()["id"])
        issue12_http.track_trip(trip_id)

        engine = create_async_engine(to_async_pg_url(issue12_http.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                await _insert_trip_load_row(
                    session,
                    issue12_http.tenant_id,
                    trip_id,
                    load_id,
                    sequence_hint=None,
                    status_within=TRIP_LOAD_STATUS_WITHIN_ACTIVE,
                )
                await session.commit()
        finally:
            await engine.dispose()

        engine = create_async_engine(to_async_pg_url(issue12_http.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                row = (
                    await db.execute(
                        text(
                            "select status_within_trip from trip_loads "
                            "where tenant_id=:t and trip_id=:trip and load_id=:l "
                            "and removed_at is null"
                        ),
                        {"t": issue12_http.tenant_id, "trip": trip_id, "l": load_id},
                    )
                ).scalar()
        finally:
            await engine.dispose()
        assert row == TRIP_LOAD_STATUS_WITHIN_ACTIVE
