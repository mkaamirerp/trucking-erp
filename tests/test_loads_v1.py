"""Load V1 tests: draft/ready, stops, broker snapshots, mark ready, dispatch excludes draft."""
from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_TENANT_RESOLUTION_SHORTCUTS"] = "true"

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")

# Auth bypass: TEST_BYPASS_AUTH=1 + tenant subdomain in Host (demo slug must exist in platform DB)
AUTH_HEADERS = {"host": "demo.truckerp.me"}


# --- Schema (no DB) ---


class TestLoadSchemaValidation:
    def test_load_number_optional_for_draft(self) -> None:
        from app.schemas.load import LoadCreate
        payload = LoadCreate(status="draft")
        assert payload.load_number is None
        assert payload.status == "draft"

    def test_stop_has_no_location_field(self) -> None:
        from app.schemas.load import LoadStopCreate
        payload = LoadStopCreate(stop_type="PICKUP", sequence=0, facility_name="Warehouse A", city="Dallas")
        assert not hasattr(payload, "location") or getattr(payload, "location", None) is None
        assert payload.facility_name == "Warehouse A"
        assert payload.city == "Dallas"

    def test_draft_and_ready_in_allowed_statuses(self) -> None:
        from app.schemas.load import ALLOWED_STATUSES
        assert "draft" in ALLOWED_STATUSES
        assert "ready" in ALLOWED_STATUSES


# --- API tests (with DB + auth/tenant override) ---


@pytest.fixture(autouse=True)
def test_bypass_env():
    """Enable middleware test bypass for Load V1 API tests (demo.truckerp.me must resolve in platform DB)."""
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    """Async client using ASGITransport to avoid event-loop conflicts with async SQLAlchemy."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    """Bypass JWT; CurrentUser.tenant_id matches Host-resolved workspace (see integration_auth)."""
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestLoadCreateDraft:
    """Create draft load with no broker."""

    async def test_create_draft_load_no_broker(self, client, override_auth_tenant) -> None:
        resp = await client.post(
            "/api/v1/loads",
            json={"status": "draft"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "draft"
        assert data.get("load_number", "").startswith("DRAFT-") or data.get("load_number")
        assert data.get("broker_id") is None
        assert data.get("broker_name_snapshot") is None
        assert data.get("stops") in (None, [])

    async def test_create_load_with_broker_and_contact_snapshots(
        self, client, override_auth_tenant
    ) -> None:
        load_num = f"L-TEST-001-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "broker_name_snapshot": "TQL",
                "broker_contact_name_snapshot": "Jane Agent",
                "broker_contact_phone_snapshot": "+15551234567",
                "broker_contact_email_snapshot": "jane@tql.com",
                "broker_load_reference": "PO-12345",
                "status": "draft",
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["broker_name_snapshot"] == "TQL"
        assert data["broker_contact_name_snapshot"] == "Jane Agent"
        assert data["broker_contact_phone_snapshot"] == "+15551234567"
        assert data["broker_load_reference"] == "PO-12345"

    async def test_create_load_with_multiple_stops(self, client, override_auth_tenant) -> None:
        load_num = f"L-STOPS-001-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "status": "draft",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "Shipper", "city": "Dallas", "state_or_province": "TX"},
                    {"stop_type": "DROP", "sequence": 1, "facility_name": "Consignee", "city": "Houston", "state_or_province": "TX"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data.get("stops", [])) == 2
        stops = sorted(data["stops"], key=lambda s: s["sequence"])
        assert stops[0]["stop_type"] == "PICKUP"
        assert stops[0]["facility_name"] == "Shipper"
        assert stops[1]["stop_type"] == "DROP"
        assert stops[1]["facility_name"] == "Consignee"

    async def test_list_loads_search_matches_load_number(self, client, override_auth_tenant) -> None:
        suffix = uuid.uuid4().hex[:8]
        num = f"SRCH-{suffix}"
        cr = await client.post(
            "/api/v1/loads",
            json={"status": "draft", "load_number": num},
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        r = await client.get(f"/api/v1/loads?search={num}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json().get("items", [])]
        assert load_id in ids


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestLoadUpdateReorderStops:
    async def test_update_reorder_stops(self, client, override_auth_tenant) -> None:
        load_num = f"L-REORDER-001-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "status": "draft",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "A"},
                    {"stop_type": "DROP", "sequence": 1, "facility_name": "B"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]

        up = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "A"},
                    {"stop_type": "PICKUP", "sequence": 1, "facility_name": "A2"},
                    {"stop_type": "DROP", "sequence": 2, "facility_name": "B"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 200
        data = up.json()
        assert len(data["stops"]) == 3
        names = [s["facility_name"] for s in sorted(data["stops"], key=lambda x: x["sequence"])]
        assert names == ["A", "A2", "B"]


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestDispatchExcludesDraft:
    async def test_draft_excluded_from_dispatch_board(self, client, override_auth_tenant) -> None:
        load_num = f"L-DRAFT-999-{uuid.uuid4().hex[:8]}"
        await client.post(
            "/api/v1/loads",
            json={"load_number": load_num, "status": "draft"},
            headers=AUTH_HEADERS,
        )
        board = await client.get("/api/v1/dispatch/board", headers=AUTH_HEADERS)
        assert board.status_code == 200
        for status_key, items in board.json().items():
            assert status_key != "draft"
            for load in items:
                assert load["status"] != "draft"


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestMarkReadyFlow:
    async def test_mark_ready_validates_minimum(self, client, override_auth_tenant) -> None:
        load_num = f"L-READY-001-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={"load_number": load_num, "status": "draft"},
            headers=AUTH_HEADERS,
        )
        load_id = cr.json()["id"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            headers=AUTH_HEADERS,
        )
        assert mr.status_code == 400
        assert "broker" in mr.json().get("detail", "").lower() or "broker_load_reference" in mr.json().get("detail", "").lower()

    async def test_mark_ready_success(self, client, override_auth_tenant) -> None:
        load_num = f"L-READY-002-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "broker_name_snapshot": "TQL",
                "broker_load_reference": "PO-999",
                "status": "draft",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "S"},
                    {"stop_type": "DROP", "sequence": 1, "facility_name": "D"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        load_id = cr.json()["id"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            headers=AUTH_HEADERS,
        )
        assert mr.status_code == 200
        assert mr.json()["status"] == "ready"
