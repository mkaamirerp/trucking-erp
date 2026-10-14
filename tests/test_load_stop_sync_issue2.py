"""Issue I2 — stop sync preserves identity, audit on removal, history protection."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
os.environ.setdefault("TEST_BYPASS_AUTH", "1")

from app.core.db_url import to_async_pg_url
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import (
    AUTH_HEADERS,
    IntegrationIsolationError,
    require_integration_tenant_database_url,
)
from tests.support.integration_test_resources import integration_scope_context


def _integration_ok() -> bool:
    try:
        require_integration_tenant_database_url(context="issue2_stop_sync")
        return True
    except IntegrationIsolationError:
        return False


SKIP = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "") or not _integration_ok()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant():
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def integration_scope(client, override_auth_tenant):
    async with integration_scope_context(client, AUTH_HEADERS, "issue2_stop_sync") as scope:
        yield scope


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
class TestLoadStopSyncIssue2:
    async def test_stop_id_preserved_on_commercial_edit(self, integration_scope) -> None:
        ln = f"I2-ID-{uuid.uuid4().hex[:8]}"
        load = await integration_scope.create_draft_load(
            ln,
            load_number=ln,
            stops=[
                {"stop_type": "PICKUP", "sequence": 0, "facility_name": "A"},
                {"stop_type": "DELIVERY", "sequence": 1, "facility_name": "B"},
            ],
        )
        load_id = load["id"]
        cv = load["concurrency_version"]
        stops = sorted(load["stops"], key=lambda s: s["sequence"])
        sid0, sid1 = stops[0]["id"], stops[1]["id"]

        up = await integration_scope.client.patch(
            f"/api/v1/loads/{load_id}",
            json={
                "expected_concurrency_version": cv,
                "commodity": "Widgets",
                "stops": [
                    {"id": sid0, "stop_type": "PICKUP", "sequence": 0, "facility_name": "A"},
                    {"id": sid1, "stop_type": "DELIVERY", "sequence": 1, "facility_name": "B-updated"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 200
        out_stops = sorted(up.json()["stops"], key=lambda s: s["sequence"])
        assert {s["id"] for s in out_stops} == {sid0, sid1}
        assert out_stops[1]["facility_name"] == "B-updated"

    async def test_operational_timestamps_preserved(self, integration_scope) -> None:
        tenant_url = integration_scope.tenant_url
        ln = f"I2-TS-{uuid.uuid4().hex[:8]}"
        load = await integration_scope.create_draft_load(
            ln,
            load_number=ln,
            stops=[{"stop_type": "PICKUP", "sequence": 0, "facility_name": "Yard"}],
        )
        load_id = load["id"]
        stop_id = load["stops"][0]["id"]
        arrived = datetime(2026, 1, 15, 10, 15, tzinfo=timezone.utc)

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(to_async_pg_url(tenant_url), pool_pre_ping=True)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            await db.execute(
                text("update load_stops set arrived_at=:a where id=:i and load_id=:l"),
                {"a": arrived, "i": stop_id, "l": load_id},
            )
            await db.commit()
        await engine.dispose()

        up = await integration_scope.client.patch(
            f"/api/v1/loads/{load_id}",
            json={
                "expected_concurrency_version": load["concurrency_version"],
                "stops": [
                    {"id": stop_id, "stop_type": "PICKUP", "sequence": 0, "facility_name": "Yard-renamed"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 200
        stop_out = up.json()["stops"][0]
        assert stop_out["id"] == stop_id
        assert stop_out["facility_name"] == "Yard-renamed"
        assert stop_out.get("arrived_at") is not None

    async def test_cannot_remove_stop_with_arrival_history(self, integration_scope) -> None:
        tenant_url = integration_scope.tenant_url
        ln = f"I2-RM-{uuid.uuid4().hex[:8]}"
        load = await integration_scope.create_draft_load(
            ln,
            load_number=ln,
            stops=[{"stop_type": "PICKUP", "sequence": 0, "facility_name": "Yard"}],
        )
        load_id = load["id"]
        stop_id = load["stops"][0]["id"]
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(to_async_pg_url(tenant_url), pool_pre_ping=True)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            await db.execute(
                text("update load_stops set arrived_at=:a where id=:i"),
                {"a": datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc), "i": stop_id},
            )
            await db.commit()
        await engine.dispose()

        up = await integration_scope.client.patch(
            f"/api/v1/loads/{load_id}",
            json={"expected_concurrency_version": load["concurrency_version"], "stops": []},
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 409
        assert up.json()["detail"]["code"] in ("LOAD_STOP_REMOVAL_FORBIDDEN", "LOAD_STOP_HISTORY_PROTECTED")

    async def test_empty_stops_removal_audited(self, integration_scope) -> None:
        ln = f"I2-EMPTY-{uuid.uuid4().hex[:8]}"
        load = await integration_scope.create_draft_load(
            ln,
            load_number=ln,
            stops=[
                {"stop_type": "PICKUP", "sequence": 0, "city": "Austin", "state_or_province": "TX"},
                {"stop_type": "DELIVERY", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
            ],
        )
        load_id = int(load["id"])
        stop_ids = [s["id"] for s in load["stops"]]

        up = await integration_scope.client.patch(
            f"/api/v1/loads/{load_id}",
            json={"expected_concurrency_version": load["concurrency_version"], "stops": []},
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 200
        assert up.json()["stops"] == []

        ar = await integration_scope.client.get(
            f"/api/v1/audit-events/by-entity?entity_type=load&entity_id={load_id}",
            headers=AUTH_HEADERS,
        )
        assert ar.status_code == 200
        events = ar.json()
        stop_events = [e for e in events if e.get("action") == "load_stops_changed"]
        assert stop_events, "expected load_stops_changed audit"
        changed = stop_events[-1].get("changed_fields") or {}
        stops_wrap = changed.get("stops") if isinstance(changed, dict) else None
        if isinstance(stops_wrap, dict) and "after" in stops_wrap:
            stops_diff = stops_wrap.get("after")
        else:
            stops_diff = stops_wrap
        if isinstance(stops_diff, str):
            stops_diff = json.loads(stops_diff)
        assert stops_diff is not None
        removed = stops_diff.get("removed") or []
        assert len(removed) == 2
        removed_ids = {int(r["stop_id"]) for r in removed}
        assert removed_ids == set(stop_ids)
        for row in removed:
            assert "before" in row and isinstance(row["before"], dict)

    async def test_partial_stop_removal_audited(self, integration_scope) -> None:
        ln = f"I2-PART-{uuid.uuid4().hex[:8]}"
        load = await integration_scope.create_draft_load(
            ln,
            load_number=ln,
            stops=[
                {"stop_type": "PICKUP", "sequence": 0, "city": "A"},
                {"stop_type": "DELIVERY", "sequence": 1, "city": "B"},
            ],
        )
        load_id = int(load["id"])
        stops = sorted(load["stops"], key=lambda s: s["sequence"])
        keep_id = stops[0]["id"]
        drop_id = stops[1]["id"]

        up = await integration_scope.client.patch(
            f"/api/v1/loads/{load_id}",
            json={
                "expected_concurrency_version": load["concurrency_version"],
                "stops": [{"id": keep_id, "stop_type": "PICKUP", "sequence": 0, "city": "A"}],
            },
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 200
        assert len(up.json()["stops"]) == 1

        ar = await integration_scope.client.get(
            f"/api/v1/audit-events/by-entity?entity_type=load&entity_id={load_id}",
            headers=AUTH_HEADERS,
        )
        stop_events = [e for e in ar.json() if e.get("action") == "load_stops_changed"]
        changed = stop_events[-1].get("changed_fields") or {}
        stops_wrap = changed.get("stops")
        if isinstance(stops_wrap, dict) and "after" in stops_wrap:
            stops_diff = stops_wrap.get("after")
        else:
            stops_diff = stops_wrap
        if isinstance(stops_diff, str):
            stops_diff = json.loads(stops_diff)
        removed = (stops_diff or {}).get("removed") or []
        assert any(int(r["stop_id"]) == int(drop_id) for r in removed)

    async def test_duplicate_stop_id_rejected(self, integration_scope) -> None:
        ln = f"I2-DUP-{uuid.uuid4().hex[:8]}"
        load = await integration_scope.create_draft_load(
            ln,
            load_number=ln,
            stops=[
                {"stop_type": "PICKUP", "sequence": 0, "city": "A"},
                {"stop_type": "DELIVERY", "sequence": 1, "city": "B"},
            ],
        )
        sid = load["stops"][0]["id"]
        up = await integration_scope.client.patch(
            f"/api/v1/loads/{load['id']}",
            json={
                "expected_concurrency_version": load["concurrency_version"],
                "stops": [
                    {"id": sid, "stop_type": "PICKUP", "sequence": 0, "city": "A"},
                    {"id": sid, "stop_type": "DELIVERY", "sequence": 1, "city": "B"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 409
        assert up.json()["detail"]["code"] == "LOAD_STOP_DUPLICATE_ID"

    async def test_invalid_stop_id_rejected(self, integration_scope) -> None:
        ln = f"I2-INV-{uuid.uuid4().hex[:8]}"
        load = await integration_scope.create_draft_load(
            ln,
            load_number=ln,
            stops=[{"stop_type": "PICKUP", "sequence": 0, "city": "A"}],
        )
        up = await integration_scope.client.patch(
            f"/api/v1/loads/{load['id']}",
            json={
                "expected_concurrency_version": load["concurrency_version"],
                "stops": [{"id": 999999999, "stop_type": "PICKUP", "sequence": 0, "city": "A"}],
            },
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 409
        assert up.json()["detail"]["code"] == "LOAD_STOP_INVALID_ID"
