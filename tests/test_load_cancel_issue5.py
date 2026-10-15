"""Issue I5 — commercial cancel via POST /loads/{id}/cancel (physical DELETE remains blocked)."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.trip_dispatch import TRIP_CONTAINER_STATUS_IN_PROGRESS
from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError, integration_tenant_db_name
from app.main import app
from app.services.loads import LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED
from tests.support.custody_http import activate_via_custody, ensure_active_terminal
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
    install_mutable_tenant_current_user_and_tenant,
)
from tests.support.integration_isolation import (
    AUTH_HEADERS,
    assert_mutating_integration_allowed,
    database_name_from_url,
    require_integration_tenant_database_url,
)
from tests.support.integration_test_resources import integration_scope_context
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
        require_integration_tenant_database_url(context="issue5_cancel")
        return True
    except IntegrationIsolationError:
        return False


_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
SKIP = _PLACEHOLDER_PLATFORM_DB or not _integration_db_configured()


async def _cancel(client: AsyncClient, load_id: int, cv: int, reason: str = "broker cancelled"):
    return await client.post(
        f"/api/v1/loads/{load_id}/cancel",
        headers=AUTH_HEADERS,
        json={"expected_concurrency_version": cv, "reason": reason},
    )


async def _mark_ready(client: AsyncClient, load: dict) -> dict:
    r = await client.post(
        f"/api/v1/loads/{load['id']}/mark-ready",
        headers=AUTH_HEADERS,
        json={"expected_concurrency_version": load["concurrency_version"]},
    )
    assert r.status_code == 200, r.text
    return r.json()


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
async def integration_scope(client, override_auth_tenant):
    async with integration_scope_context(client, AUTH_HEADERS, "issue5_cancel") as scope:
        yield scope


@pytest.fixture
async def issue5_cancel_http(client, override_auth_tenant, integration_scope):
    tenant_id = await platform_tenant_id_for_slug()
    await assert_mutating_integration_allowed(
        tenant_id=tenant_id,
        host=AUTH_HEADERS["host"],
        context="issue5_cancel",
    )

    async def new_draft(**extra) -> dict:
        r = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"I5C-{uuid.uuid4().hex[:8]}", **extra},
        )
        assert r.status_code == 201, r.text
        return r.json()

    ctx = SimpleNamespace(client=client, new_draft=new_draft, scope=integration_scope, tenant_id=tenant_id)
    yield ctx


@pytest.mark.skipif(SKIP, reason="integration tenant DB not configured")
@pytest.mark.asyncio
class TestLoadCancelIssue5:
    async def test_physical_delete_still_blocked(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft()
        r = await issue5_cancel_http.client.delete(
            f"/api/v1/loads/{load['id']}",
            headers=AUTH_HEADERS,
            params={"expected_concurrency_version": load["concurrency_version"]},
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED

    async def test_draft_cancel(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft()
        rate = load.get("rate")
        r = await _cancel(issue5_cancel_http.client, int(load["id"]), int(load["concurrency_version"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "cancelled"
        assert body.get("rate") == rate

    async def test_ready_cancel(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft(
            broker_name_snapshot="Broker",
            broker_load_reference=f"REF-{uuid.uuid4().hex[:8]}",
            stops=_VALID_STOPS,
            rate=1500.0,
        )
        ready = await _mark_ready(issue5_cancel_http.client, load)
        r = await _cancel(issue5_cancel_http.client, int(ready["id"]), int(ready["concurrency_version"]))
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"
        assert float(r.json()["rate"]) == 1500.0

    async def test_active_trip_load_rejected(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft(
            broker_name_snapshot="Broker",
            broker_load_reference=f"REF-{uuid.uuid4().hex[:8]}",
            stops=_VALID_STOPS,
        )
        ready = await _mark_ready(issue5_cancel_http.client, load)
        load_id = int(ready["id"])
        r_trip = await issue5_cancel_http.scope.post_planned_trip([load_id])
        trip_id = int(r_trip.json()["id"])
        d_id, t_id, r_id = await issue5_cancel_http.scope.create_fleet_bundle(f"I5C-{uuid.uuid4().hex[:6]}")
        assert (
            await issue5_cancel_http.client.put(
                f"/api/v1/trips/{trip_id}/assignment",
                headers=AUTH_HEADERS,
                json={"driver_id": d_id, "truck_id": t_id, "trailer_id": r_id},
            )
        ).status_code == 200
        assert (
            await issue5_cancel_http.client.post(
                f"/api/v1/trips/{trip_id}/execution-signal",
                headers=AUTH_HEADERS,
                json={"source": "dispatcher_manual"},
            )
        ).json()["status"] == TRIP_CONTAINER_STATUS_IN_PROGRESS
        assert (await activate_via_custody(issue5_cancel_http.client, AUTH_HEADERS, trip_id, load_id)).status_code == 200
        gr = await issue5_cancel_http.client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        cv = int(gr.json()["concurrency_version"])

        r = await _cancel(issue5_cancel_http.client, load_id, cv)
        assert r.status_code == 409
        assert _detail_code(r.json()) == "LOAD_CANCEL_ACTIVE_TRIP_EXECUTION"

    async def test_unresolved_custody_rejected(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft(
            broker_name_snapshot="Broker",
            broker_load_reference=f"REF-{uuid.uuid4().hex[:8]}",
            stops=_VALID_STOPS,
        )
        ready = await _mark_ready(issue5_cancel_http.client, load)
        load_id = int(ready["id"])
        terminal_id = await ensure_active_terminal(issue5_cancel_http.client, AUTH_HEADERS)
        tenant_url = to_async_pg_url(require_integration_tenant_database_url(context="issue5_cancel_custody"))
        engine = create_async_engine(tenant_url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                await session.execute(
                    text(
                        "UPDATE loads SET custody_owner = 'terminal', custody_terminal_id = :tid, "
                        "custody_trip_id = NULL WHERE id = :lid"
                    ),
                    {"tid": terminal_id, "lid": load_id},
                )
                await session.commit()
        finally:
            await engine.dispose()
        r = await _cancel(issue5_cancel_http.client, load_id, int(ready["concurrency_version"]))
        assert r.status_code == 409
        assert _detail_code(r.json()) == "LOAD_CANCEL_UNRESOLVED_CUSTODY"

    async def test_historical_trip_load_preserved(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft(
            broker_name_snapshot="Broker",
            broker_load_reference=f"REF-{uuid.uuid4().hex[:8]}",
            stops=_VALID_STOPS,
        )
        ready = await _mark_ready(issue5_cancel_http.client, load)
        load_id = int(ready["id"])
        trip_id = int((await issue5_cancel_http.scope.post_planned_trip([load_id])).json()["id"])
        r = await _cancel(issue5_cancel_http.client, load_id, int(ready["concurrency_version"]))
        assert r.status_code == 200
        tenant_url = to_async_pg_url(require_integration_tenant_database_url(context="issue5_cancel_check"))
        engine = create_async_engine(tenant_url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                n = await session.scalar(
                    text(
                        "SELECT count(*)::int FROM trip_loads WHERE trip_id = :tid AND load_id = :lid"
                    ),
                    {"tid": trip_id, "lid": load_id},
                )
                assert int(n or 0) == 1
        finally:
            await engine.dispose()

    async def test_audit_event_and_actor(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft()
        load_id = int(load["id"])
        r = await _cancel(issue5_cancel_http.client, load_id, int(load["concurrency_version"]), reason="test audit")
        assert r.status_code == 200
        ar = await issue5_cancel_http.client.get(
            "/api/v1/audit-events/by-entity",
            headers=AUTH_HEADERS,
            params={"entity_type": "load", "entity_id": str(load_id), "limit": 20},
        )
        assert ar.status_code == 200
        actions = [row.get("action") for row in ar.json()]
        assert "load_cancelled" in actions

    async def test_concurrency_conflict(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft()
        r = await _cancel(issue5_cancel_http.client, int(load["id"]), 99999)
        assert r.status_code == 409
        assert r.json().get("detail", {}).get("code") == "LOAD_VERSION_CONFLICT"

    async def test_tenant_isolation(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft()
        holder = {"tenant_id": issue5_cancel_http.tenant_id}
        install_mutable_tenant_current_user_and_tenant(app, holder)
        holder["tenant_id"] = issue5_cancel_http.tenant_id + 9_999_999
        r = await _cancel(issue5_cancel_http.client, int(load["id"]), int(load["concurrency_version"]))
        assert r.status_code == 404
        install_host_aligned_current_user_and_tenant(app)

    async def test_repeat_cancel_idempotent(self, issue5_cancel_http) -> None:
        load = await issue5_cancel_http.new_draft()
        load_id = int(load["id"])
        r1 = await _cancel(issue5_cancel_http.client, load_id, int(load["concurrency_version"]))
        assert r1.status_code == 200
        cv = int(r1.json()["concurrency_version"])
        r2 = await _cancel(issue5_cancel_http.client, load_id, cv, reason="again")
        assert r2.status_code == 200
        assert r2.json()["status"] == "cancelled"
        assert int(r2.json()["concurrency_version"]) == cv
