"""Issue 5 Phase 2 — temporary block on physical DELETE /api/v1/loads/{id}."""

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

from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError, integration_tenant_db_name
from app.main import app
from app.services.loads import LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED, delete_load
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
        require_integration_tenant_database_url(context="issue5_delete_guard_precheck")
        return True
    except IntegrationIsolationError:
        return False


_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
SKIP_ISSUE5_HTTP = _PLACEHOLDER_PLATFORM_DB or not _integration_db_configured()


async def _cleanup_trip_rows(db: AsyncSession, tenant_id: int, trip_id: int) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context="issue5_cleanup_trip")
    await db.execute(
        text("delete from trip_loads where tenant_id=:t and trip_id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    await db.execute(
        text("delete from trips where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": trip_id},
    )


async def _assert_trip_absent(db: AsyncSession, tenant_id: int, trip_id: int) -> None:
    n = await db.scalar(
        text("select count(*) from trips where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    assert int(n or 0) == 0, f"trip row still present after cleanup (tenant_id={tenant_id}, id={trip_id})"
    m = await db.scalar(
        text("select count(*) from trip_loads where tenant_id=:t and trip_id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    assert int(m or 0) == 0, f"trip_loads still present after cleanup (trip_id={trip_id})"


async def _cleanup_load_rows(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context="issue5_cleanup_load")
    await db.execute(
        text("delete from trip_loads where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from audit_events where tenant_id=:t and entity_type='load' and entity_id=:e"),
        {"t": tenant_id, "e": str(load_id)},
    )
    await db.execute(
        text("delete from load_stops where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.commit()


async def _assert_load_absent(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    n = await db.scalar(
        text("select count(*) from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    assert int(n or 0) == 0, f"loads row still present after cleanup (tenant_id={tenant_id}, id={load_id})"


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
def issue5_integration_gate():
    try:
        tenant_url = require_integration_tenant_database_url(context="issue5_delete_guard")
    except IntegrationIsolationError as exc:
        pytest.skip(f"Issue 5 delete guard HTTP tests require isolated tenant DB: {exc}")
    db_name = database_name_from_url(tenant_url)
    expected = integration_tenant_db_name()
    if db_name != expected:
        pytest.skip(f"Issue 5 tests require database {expected!r}, got {db_name!r}")
    return {"tenant_database_url": tenant_url, "tenant_db_name": db_name}


@pytest.fixture
async def issue5_http(client, override_auth_tenant, issue5_integration_gate):
    gate = issue5_integration_gate
    tenant_id = await platform_tenant_id_for_slug()
    await assert_mutating_integration_allowed(
        tenant_id=tenant_id,
        host=AUTH_HEADERS["host"],
        context="issue5_delete_guard",
    )

    created_load_ids: list[int] = []
    created_trip_ids: list[int] = []

    async def new_draft(**extra) -> dict:
        r = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"I5-{uuid.uuid4().hex[:8]}", **extra},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        created_load_ids.append(int(body["id"]))
        return body

    async def new_planned_trip(load_ids: list[int]) -> dict:
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "load_ids": [int(x) for x in load_ids]},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        created_trip_ids.append(int(body["id"]))
        return body

    ctx = SimpleNamespace(
        client=client,
        new_draft=new_draft,
        new_planned_trip=new_planned_trip,
        tenant_id=tenant_id,
        created_trip_ids=created_trip_ids,
    )
    try:
        yield ctx
    finally:
        if created_load_ids or created_trip_ids:
            engine = create_async_engine(to_async_pg_url(gate["tenant_database_url"]), pool_pre_ping=True)
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            try:
                async with Session() as db:
                    for trip_id in reversed(created_trip_ids):
                        await _cleanup_trip_rows(db, tenant_id, trip_id)
                    for load_id in reversed(created_load_ids):
                        await _cleanup_load_rows(db, tenant_id, load_id)
                    for trip_id in created_trip_ids:
                        await _assert_trip_absent(db, tenant_id, trip_id)
                    for load_id in created_load_ids:
                        await _assert_load_absent(db, tenant_id, load_id)
            finally:
                await engine.dispose()


async def _delete(client: AsyncClient, load_id: int, cv: int = 1):
    return await client.delete(
        f"/api/v1/loads/{load_id}",
        headers=AUTH_HEADERS,
        params={"expected_concurrency_version": cv},
    )


@pytest.mark.skipif(SKIP_ISSUE5_HTTP, reason="integration tenant DB not configured")
@pytest.mark.asyncio
class TestLoadPhysicalDeleteGuardIssue5:
    async def test_draft_load_returns_409_disabled(self, issue5_http) -> None:
        load = await issue5_http.new_draft()
        r = await _delete(issue5_http.client, int(load["id"]), int(load["concurrency_version"]))
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED

    async def test_ready_load_returns_409_disabled(self, issue5_http) -> None:
        load = await issue5_http.new_draft(
            broker_name_snapshot="Broker",
            broker_load_reference=f"REF-{uuid.uuid4().hex[:8]}",
            stops=_VALID_STOPS,
        )
        mr = await issue5_http.client.post(
            f"/api/v1/loads/{load['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": load["concurrency_version"]},
        )
        assert mr.status_code == 200, mr.text
        ready = mr.json()
        r = await _delete(issue5_http.client, int(ready["id"]), int(ready["concurrency_version"]))
        assert r.status_code == 409
        assert _detail_code(r.json()) == LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED

    async def test_load_with_trip_membership_returns_409_disabled(self, issue5_http) -> None:
        load = await issue5_http.new_draft(
            broker_name_snapshot="Broker",
            broker_load_reference="REF-I5",
            stops=_VALID_STOPS,
        )
        cv = int(load["concurrency_version"])
        mr = await issue5_http.client.post(
            f"/api/v1/loads/{load['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": cv},
        )
        assert mr.status_code == 200, mr.text
        await issue5_http.new_planned_trip([int(load["id"])])
        assert len(issue5_http.created_trip_ids) == 1
        r = await _delete(issue5_http.client, int(load["id"]), int(load["concurrency_version"]))
        assert r.status_code == 409
        assert _detail_code(r.json()) == LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED

    async def test_missing_load_returns_404(self, issue5_http) -> None:
        r = await _delete(issue5_http.client, 999_999_999, 1)
        assert r.status_code == 404

    async def test_wrong_tenant_returns_404(self, issue5_http) -> None:
        load = await issue5_http.new_draft()
        load_id = int(load["id"])
        holder = {"tenant_id": issue5_http.tenant_id}
        install_mutable_tenant_current_user_and_tenant(app, holder)
        holder["tenant_id"] = 53 if issue5_http.tenant_id != 53 else 62
        r = await _delete(issue5_http.client, load_id, 1)
        assert r.status_code == 404
        install_host_aligned_current_user_and_tenant(app)

    async def test_row_and_children_unchanged_after_409(self, issue5_http) -> None:
        load = await issue5_http.new_draft(stops=_VALID_STOPS)
        load_id = int(load["id"])
        stops_before = len(load.get("stops") or [])
        r = await _delete(issue5_http.client, load_id, int(load["concurrency_version"]))
        assert r.status_code == 409
        gr = await issue5_http.client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        assert gr.status_code == 200, gr.text
        body = gr.json()
        assert body["id"] == load_id
        assert len(body.get("stops") or []) == stops_before

    async def test_service_delete_load_cannot_bypass_guard(self, issue5_http, issue5_integration_gate) -> None:
        load = await issue5_http.new_draft()
        load_id = int(load["id"])
        engine = create_async_engine(
            to_async_pg_url(issue5_integration_gate["tenant_database_url"]), pool_pre_ping=True
        )
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await delete_load(
                        db,
                        issue5_http.tenant_id,
                        load_id,
                        expected_concurrency_version=int(load["concurrency_version"]),
                    )
                assert exc_info.value.status_code == 409
                n = await db.scalar(
                    text("select count(*) from loads where tenant_id=:t and id=:i"),
                    {"t": issue5_http.tenant_id, "i": load_id},
                )
                assert int(n or 0) == 1
        finally:
            await engine.dispose()

    async def test_unauthenticated_delete_rejected(self, client) -> None:
        install_host_aligned_current_user_and_tenant(app)
        old = os.environ.pop("TEST_BYPASS_AUTH", None)
        try:
            r = await client.delete(
                "/api/v1/loads/1",
                headers=AUTH_HEADERS,
                params={"expected_concurrency_version": 1},
            )
            assert r.status_code in (401, 403)
        finally:
            if old is not None:
                os.environ["TEST_BYPASS_AUTH"] = old
            clear_current_user_and_tenant_overrides(app)


def test_guard_constant_exported() -> None:
    assert LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED == "LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED"
