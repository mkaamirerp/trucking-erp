"""Issue 0A — executable legacy writer freeze for generic Load create / PATCH.

Contract A (reject): Load create accepts only status=draft; Load create/PATCH reject legacy operational
statuses and any driver_id / truck_id / trailer_id with explicit 409 codes. Historical legacy rows stay
readable and commercially editable when status/assignment are omitted. Load writes never mint or cancel
dispatch_trips.

Unit gates need no database. Integration gates need DATABASE_URL + TENANT_DATABASE_URL pointing at the
dedicated integration tenant (tenant_pytest); see scripts/run_fuel_pytest.sh.
"""

from __future__ import annotations

import inspect
import os
import uuid
from pathlib import Path
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
    LEGACY_LOAD_ASSIGNMENT_DEPRECATED,
    LEGACY_LOAD_OPERATIONAL_STATUSES,
    LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED,
    LEGACY_LOAD_STATUS_TRANSITION_BLOCKED,
    LOAD_CREATE_STATUS_MUST_BE_DRAFT,
    LOAD_STATUS_NOT_WRITABLE,
    TRIP_CONTAINER_STATUS_PLANNED,
)
from app.core.db_url import to_async_pg_url
from app.main import app
from app.schemas.load import LoadCreate, LoadResponse, LoadUpdate
from app.services import dispatch_trips as dispatch_trips_service
from app.services import loads as loads_service
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.legacy_dispatch_test_seed import seed_load_dispatched_legacy_state
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_HEADERS = {"host": "pytest.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
REQUIRES_INTEGRATION = _PLACEHOLDER_PLATFORM_DB or not (
    os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
)

ASSIGNMENT_FIELDS = ("driver_id", "truck_id", "trailer_id")


def _code(exc: HTTPException) -> str | None:
    return exc.detail.get("code") if isinstance(exc.detail, dict) else None


def _detail_code(payload: dict) -> str | None:
    d = payload.get("detail")
    return d.get("code") if isinstance(d, dict) else None


class _UntouchableDb:
    """Any DB access means a guard ran too late."""

    def __getattr__(self, name: str):
        raise AssertionError(f"db.{name} accessed before Issue 0A guard rejected the payload")


# ---------------------------------------------------------------------------
# Unit gates (no database)
# ---------------------------------------------------------------------------


class TestCreateFreezeUnit:
    @pytest.mark.parametrize("legacy_status", ["assigned", "dispatched", "in_transit"])
    async def test_create_rejects_legacy_operational_status(self, legacy_status: str) -> None:
        with pytest.raises(HTTPException) as ei:
            await loads_service.create_load(_UntouchableDb(), 1, LoadCreate(status=legacy_status))
        assert ei.value.status_code == 409
        assert _code(ei.value) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED

    async def test_create_rejects_ready(self) -> None:
        with pytest.raises(HTTPException) as ei:
            await loads_service.create_load(_UntouchableDb(), 1, LoadCreate(status="ready"))
        assert ei.value.status_code == 409
        assert _code(ei.value) == LOAD_CREATE_STATUS_MUST_BE_DRAFT

    @pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
    @pytest.mark.parametrize("value", [7, None])
    async def test_create_rejects_assignment_fields(self, field: str, value) -> None:
        with pytest.raises(HTTPException) as ei:
            await loads_service.create_load(_UntouchableDb(), 1, LoadCreate(status="draft", **{field: value}))
        assert ei.value.status_code == 409
        assert _code(ei.value) == LEGACY_LOAD_ASSIGNMENT_DEPRECATED


class TestUpdateFreezeUnit:
    @pytest.fixture
    def stored(self, monkeypatch):
        row = SimpleNamespace(status="draft")

        async def _fake_get_load(db, tenant_id, load_id):
            return row

        monkeypatch.setattr(loads_service, "get_load", _fake_get_load)
        return row

    @pytest.mark.parametrize("legacy_status", sorted(LEGACY_LOAD_OPERATIONAL_STATUSES))
    async def test_patch_rejects_every_legacy_status_target(self, stored, legacy_status: str) -> None:
        with pytest.raises(HTTPException) as ei:
            await loads_service.update_load(
                _UntouchableDb(), 1, 1, LoadUpdate(expected_concurrency_version=1, status=legacy_status)
            )
        assert ei.value.status_code == 409
        assert _code(ei.value) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED

    @pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
    async def test_patch_rejects_assignment_fields(self, stored, field: str) -> None:
        with pytest.raises(HTTPException) as ei:
            await loads_service.update_load(
                _UntouchableDb(), 1, 1, LoadUpdate(expected_concurrency_version=1, **{field: 3})
            )
        assert _code(ei.value) == LEGACY_LOAD_ASSIGNMENT_DEPRECATED

    @pytest.mark.parametrize("source", ["seed", "migration", "ui"])
    async def test_source_seed_is_not_a_bypass(self, stored, source: str) -> None:
        with pytest.raises(HTTPException) as ei:
            await loads_service.update_load(
                _UntouchableDb(),
                1,
                1,
                LoadUpdate(expected_concurrency_version=1, status="dispatched"),
                source=source,
            )
        assert _code(ei.value) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED

    @pytest.mark.parametrize("stored_status", ["draft", "dispatched"])
    async def test_explicit_null_status_rejected_before_mutation(self, stored, stored_status: str) -> None:
        stored.status = stored_status
        payload = LoadUpdate(expected_concurrency_version=1, status=None)
        assert "status" in payload.model_fields_set
        with pytest.raises(HTTPException) as ei:
            await loads_service.update_load(_UntouchableDb(), 1, 1, payload)
        assert ei.value.status_code == 409
        assert _code(ei.value) == LOAD_STATUS_NOT_WRITABLE

    @pytest.mark.parametrize("target", ["draft", "ready"])
    async def test_legacy_row_status_change_blocked(self, stored, target: str) -> None:
        stored.status = "dispatched"
        with pytest.raises(HTTPException) as ei:
            await loads_service.update_load(
                _UntouchableDb(), 1, 1, LoadUpdate(expected_concurrency_version=1, status=target)
            )
        assert _code(ei.value) == LEGACY_LOAD_STATUS_TRANSITION_BLOCKED


class TestLegacyMintCancelReachability:
    def test_load_service_has_no_mint_cancel_or_seed_branch(self) -> None:
        src = inspect.getsource(loads_service)
        assert "ensure_active_trip_for_freight_load" not in src
        assert "cancel_active_trip_for_load" not in src
        assert '"seed"' not in src
        assert not hasattr(loads_service, "dispatch_trips_service")

    def test_legacy_helpers_still_exist_for_tests_and_issue_0b(self) -> None:
        assert callable(dispatch_trips_service.ensure_active_trip_for_freight_load)
        assert callable(dispatch_trips_service.cancel_active_trip_for_load)

    def test_seed_scripts_do_not_patch_loads_or_write_operational_state(self) -> None:
        seed = (REPO_ROOT / "app/scripts/seed_demo_operational_loads.py").read_text()
        assert 'source="seed"' not in seed
        assert "update_load" not in seed
        raw = (REPO_ROOT / "seed_dispatch.py").read_text()
        for legacy in ("unassigned", "assigned", "dispatched", "driver_id", "truck_id", "trailer_id"):
            assert legacy not in raw, legacy


class TestHistoricalReadModelUnit:
    @pytest.mark.parametrize("legacy_status", sorted(LEGACY_LOAD_OPERATIONAL_STATUSES))
    def test_response_still_reads_legacy_rows(self, legacy_status: str) -> None:
        resp = LoadResponse.model_validate(
            {
                "id": 1,
                "load_number": "HIST-1",
                "status": legacy_status,
                "driver_id": 5,
                "truck_id": 6,
                "trip_number": "IKL10001",
                "active_dispatch_trip_id": 42,
                "active_trip_id": 43,
            }
        )
        assert resp.status == legacy_status
        assert resp.trip_number == "IKL10001"
        assert resp.active_dispatch_trip_id == 42
        assert resp.driver_id == 5


def test_mark_ready_route_still_registered() -> None:
    paths = {(r.path, m) for r in app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/loads/{load_id}/mark-ready", "POST") in paths
    assert ("/api/v1/trips", "POST") in paths


# ---------------------------------------------------------------------------
# Integration gates (tenant_pytest via HTTP + direct counts)
# ---------------------------------------------------------------------------


def _tenant_async_url() -> str:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    assert raw
    return to_async_pg_url(raw)


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
async def tenant_session():
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield Session
    finally:
        await engine.dispose()


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> str:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200
    body = r0.json()
    if body.get("prefix_locked") and body.get("trip_number_prefix"):
        return str(body["trip_number_prefix"])
    prefix = f"Z{uuid.uuid4().hex[:7].upper()}"
    r1 = await client.put("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS, json={"trip_number_prefix": prefix})
    assert r1.status_code == 200, r1.text
    return prefix


async def _freight_counts(Session, load_id: int | None = None) -> dict[str, int]:
    async with Session() as s:
        out = {
            "dispatch_trips_total": int((await s.execute(text("SELECT count(*) FROM dispatch_trips"))).scalar() or 0),
            "trips_active_total": int(
                (await s.execute(text("SELECT count(*) FROM trips WHERE status = 'active'"))).scalar() or 0
            ),
        }
        if load_id is not None:
            out["dispatch_trips_for_load"] = int(
                (
                    await s.execute(text("SELECT count(*) FROM dispatch_trips WHERE load_id = :lid"), {"lid": load_id})
                ).scalar()
                or 0
            )
            out["trip_loads_for_load"] = int(
                (
                    await s.execute(text("SELECT count(*) FROM trip_loads WHERE load_id = :lid"), {"lid": load_id})
                ).scalar()
                or 0
            )
        return out


async def _new_draft(client: AsyncClient, tag: str, **extra) -> dict:
    r = await client.post(
        "/api/v1/loads",
        headers=AUTH_HEADERS,
        json={"status": "draft", "load_number": f"{tag}-{uuid.uuid4().hex[:8]}", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _load_number_exists(client: AsyncClient, load_number: str) -> bool:
    r = await client.get(f"/api/v1/loads?search={load_number}", headers=AUTH_HEADERS)
    assert r.status_code == 200
    return any(x.get("load_number") == load_number for x in r.json().get("items", []))


@pytest.mark.skipif(REQUIRES_INTEGRATION, reason="integration tenant DB required")
class TestLoadWriterFreezeHttp:
    @pytest.mark.parametrize("legacy_status", ["assigned", "dispatched", "in_transit"])
    async def test_post_legacy_status_creates_nothing(self, client, override_auth_tenant, legacy_status) -> None:
        ln = f"I0A-C-{uuid.uuid4().hex[:8]}"
        r = await client.post("/api/v1/loads", headers=AUTH_HEADERS, json={"status": legacy_status, "load_number": ln})
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
        assert not await _load_number_exists(client, ln)

    @pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
    async def test_post_assignment_rejected(self, client, override_auth_tenant, field) -> None:
        ln = f"I0A-A-{uuid.uuid4().hex[:8]}"
        r = await client.post(
            "/api/v1/loads", headers=AUTH_HEADERS, json={"status": "draft", "load_number": ln, field: 1}
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LEGACY_LOAD_ASSIGNMENT_DEPRECATED
        assert not await _load_number_exists(client, ln)

    async def test_post_default_creates_draft(self, client, override_auth_tenant) -> None:
        ln = f"I0A-D-{uuid.uuid4().hex[:8]}"
        r = await client.post("/api/v1/loads", headers=AUTH_HEADERS, json={"load_number": ln})
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "draft"

    @pytest.mark.parametrize("legacy_status", ["assigned", "in_transit", "dispatched"])
    async def test_patch_draft_to_legacy_status_blocked(self, client, override_auth_tenant, legacy_status) -> None:
        created = await _new_draft(client, "I0A-P")
        r = await client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={"status": legacy_status, "expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
        after = (await client.get(f"/api/v1/loads/{created['id']}", headers=AUTH_HEADERS)).json()
        assert after["status"] == "draft"
        assert after["concurrency_version"] == created["concurrency_version"]

    async def test_patch_null_status_controlled_4xx_and_row_unchanged(self, client, override_auth_tenant) -> None:
        created = await _new_draft(client, "I0A-N")
        r = await client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={"status": None, "expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LOAD_STATUS_NOT_WRITABLE
        after = (await client.get(f"/api/v1/loads/{created['id']}", headers=AUTH_HEADERS)).json()
        assert after["status"] == "draft"
        assert after["concurrency_version"] == created["concurrency_version"]

    @pytest.mark.parametrize("field", ASSIGNMENT_FIELDS)
    async def test_patch_assignment_blocked(self, client, override_auth_tenant, field) -> None:
        created = await _new_draft(client, "I0A-PA")
        r = await client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={field: None, "expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LEGACY_LOAD_ASSIGNMENT_DEPRECATED

    async def test_load_post_and_patch_mint_no_dispatch_trip_or_active_trip(
        self, client, override_auth_tenant, tenant_session, locked_prefix
    ) -> None:
        before = await _freight_counts(tenant_session)
        created = await _new_draft(client, "I0A-M")
        lid = created["id"]
        cv = created["concurrency_version"]
        ok = await client.patch(
            f"/api/v1/loads/{lid}",
            headers=AUTH_HEADERS,
            json={"internal_notes": "commercial edit", "commodity": "Paper", "expected_concurrency_version": cv},
        )
        assert ok.status_code == 200, ok.text
        cv = ok.json()["concurrency_version"]
        for bad in ({"status": "dispatched"}, {"status": "assigned"}, {"driver_id": 1, "truck_id": 1}):
            r = await client.patch(
                f"/api/v1/loads/{lid}", headers=AUTH_HEADERS, json={**bad, "expected_concurrency_version": cv}
            )
            assert r.status_code == 409, r.text
        after = await _freight_counts(tenant_session, lid)
        assert after["dispatch_trips_for_load"] == 0
        assert after["trip_loads_for_load"] == 0
        assert after["dispatch_trips_total"] == before["dispatch_trips_total"]
        assert after["trips_active_total"] == before["trips_active_total"]

    async def test_historical_dispatched_row_commercial_edit(
        self, client, override_auth_tenant, tenant_session, locked_prefix, monkeypatch
    ) -> None:
        created = await _new_draft(client, "I0A-H")
        lid = created["id"]
        tenant_id = await platform_tenant_id_for_slug()
        async with tenant_session() as s:
            await seed_load_dispatched_legacy_state(s, tenant_id, lid)
        hist = (await client.get(f"/api/v1/loads/{lid}", headers=AUTH_HEADERS)).json()
        assert hist["status"] == "dispatched"
        assert hist["trip_number"]
        assert hist["active_dispatch_trip_id"] is not None
        before = await _freight_counts(tenant_session, lid)

        async def _forbidden(*_a, **_k):
            raise AssertionError("Load PATCH must not call legacy mint/cancel helpers")

        monkeypatch.setattr(dispatch_trips_service, "ensure_active_trip_for_freight_load", _forbidden)
        monkeypatch.setattr(dispatch_trips_service, "cancel_active_trip_for_load", _forbidden)

        r = await client.patch(
            f"/api/v1/loads/{lid}",
            headers=AUTH_HEADERS,
            json={
                "internal_notes": "historical commercial edit",
                "commodity": "Steel coils",
                "broker_load_reference": "HIST-REF-1",
                "expected_concurrency_version": hist["concurrency_version"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["internal_notes"] == "historical commercial edit"
        assert body["commodity"] == "Steel coils"
        assert body["broker_load_reference"] == "HIST-REF-1"
        assert body["status"] == "dispatched"
        assert body["trip_number"] == hist["trip_number"]
        assert body["active_dispatch_trip_id"] == hist["active_dispatch_trip_id"]
        assert body["active_trip_id"] == hist["active_trip_id"]
        assert await _freight_counts(tenant_session, lid) == before

    async def test_planned_trip_create_still_works(self, client, override_auth_tenant, locked_prefix) -> None:
        r = await client.post(
            "/api/v1/trips",
            headers=AUTH_HEADERS,
            json={"status": "planned", "job_type": "freight_load", "load_ids": []},
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == TRIP_CONTAINER_STATUS_PLANNED
        assert r.json().get("trip_number")

    async def test_mark_ready_still_moves_draft_to_ready(self, client, override_auth_tenant) -> None:
        created = await _new_draft(
            client,
            "I0A-R",
            broker_name_snapshot="Gate Broker",
            broker_load_reference=f"REF-{uuid.uuid4().hex[:6]}",
            stops=[
                {"stop_type": "PICKUP", "sequence": 0, "city": "Austin", "state_or_province": "TX"},
                {"stop_type": "DROP", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
            ],
        )
        r = await client.post(
            f"/api/v1/loads/{created['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ready"
