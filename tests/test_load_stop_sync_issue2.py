"""Issue I2 — stop sync preserves identity and operational timestamps."""

from __future__ import annotations

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


@pytest.mark.skipif(SKIP, reason="tenant_pytest required")
class TestLoadStopSyncIssue2:
    async def test_stop_id_preserved_on_commercial_edit(
        self, client: AsyncClient, override_auth_tenant
    ) -> None:
        ln = f"I2-ID-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": ln,
                "status": "draft",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "A"},
                    {"stop_type": "DELIVERY", "sequence": 1, "facility_name": "B"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load = cr.json()
        load_id = load["id"]
        cv = load["concurrency_version"]
        stops = sorted(load["stops"], key=lambda s: s["sequence"])
        sid0, sid1 = stops[0]["id"], stops[1]["id"]

        up = await client.patch(
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

    async def test_operational_timestamps_preserved(
        self, client: AsyncClient, override_auth_tenant
    ) -> None:
        tenant_url = require_integration_tenant_database_url(context="issue2_ts")
        ln = f"I2-TS-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": ln,
                "status": "draft",
                "stops": [{"stop_type": "PICKUP", "sequence": 0, "facility_name": "Yard"}],
            },
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load = cr.json()
        load_id = load["id"]
        stop_id = load["stops"][0]["id"]
        arrived = datetime(2026, 1, 15, 10, 15, tzinfo=timezone.utc)

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(to_async_pg_url(tenant_url), pool_pre_ping=True)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            await db.execute(
                text(
                    "update load_stops set arrived_at=:a where id=:i and load_id=:l"
                ),
                {"a": arrived, "i": stop_id, "l": load_id},
            )
            await db.commit()
        await engine.dispose()

        up = await client.patch(
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
