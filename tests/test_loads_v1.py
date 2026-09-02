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

    def test_target_and_legacy_status_sets_are_separate(self) -> None:
        from app.schemas.load import (
            ALLOWED_STATUSES,
            DISPATCH_STATUSES,
            GENERIC_LOAD_WRITE_STATUSES,
            LEGACY_LOAD_OPERATIONAL_STATUSES,
            LOAD_TARGET_STATUSES,
        )

        assert "draft" in ALLOWED_STATUSES
        assert "ready" in ALLOWED_STATUSES
        assert "cancelled" in LOAD_TARGET_STATUSES
        assert "cancelled" not in DISPATCH_STATUSES
        assert GENERIC_LOAD_WRITE_STATUSES == {"draft", "ready"}
        assert "dispatched" in LEGACY_LOAD_OPERATIONAL_STATUSES

    @pytest.mark.parametrize(
        "legacy_status",
        [
            "unassigned",
            "assigned",
            "dispatched",
            "arrived_pickup",
            "in_transit",
            "arrived_delivery",
            "delivered",
            "issue_hold",
            "cancelled",
        ],
    )
    def test_new_load_rejects_non_generic_write_status(self, legacy_status: str) -> None:
        from pydantic import ValidationError

        from app.schemas.load import LoadCreate

        with pytest.raises(ValidationError, match="New Loads may use status draft or ready only"):
            LoadCreate(status=legacy_status)

    @pytest.mark.parametrize("legacy_status", ["assigned", "dispatched", "in_transit", "delivered"])
    def test_load_response_preserves_legacy_read_compatibility(self, legacy_status: str) -> None:
        from app.schemas.load import LoadResponse

        response = LoadResponse(id=1, status=legacy_status)
        assert response.status == legacy_status


class TestLoadStatusWriteBoundary:
    @pytest.mark.parametrize("legacy_status", ["assigned", "in_transit", "delivered", "issue_hold"])
    def test_new_legacy_transition_is_rejected(self, legacy_status: str) -> None:
        from fastapi import HTTPException

        from app.services.loads import _validate_generic_load_status_transition

        with pytest.raises(HTTPException) as exc:
            _validate_generic_load_status_transition(
                old_status="ready", new_status=legacy_status, source="ui"
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "LEGACY_LOAD_STATUS_WRITE_DEPRECATED"

    def test_dispatched_keeps_existing_error_contract(self) -> None:
        from fastapi import HTTPException

        from app.services.loads import _validate_generic_load_status_transition

        with pytest.raises(HTTPException) as exc:
            _validate_generic_load_status_transition(
                old_status="ready", new_status="dispatched", source="ui"
            )
        assert exc.value.detail["code"] == "LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED"

    def test_generic_cancel_requires_explicit_commercial_workflow(self) -> None:
        from fastapi import HTTPException

        from app.services.loads import _validate_generic_load_status_transition

        with pytest.raises(HTTPException) as exc:
            _validate_generic_load_status_transition(
                old_status="ready", new_status="cancelled", source="ui"
            )
        assert exc.value.detail["code"] == "LOAD_COMMERCIAL_CANCEL_ACTION_REQUIRED"

    def test_unchanged_legacy_status_and_seed_transition_remain_compatible(self) -> None:
        from app.services.loads import _validate_generic_load_status_transition

        _validate_generic_load_status_transition(
            old_status="dispatched", new_status="dispatched", source="ui"
        )
        _validate_generic_load_status_transition(
            old_status="ready", new_status="in_transit", source="seed"
        )


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

    @pytest.mark.parametrize("legacy_status", ["assigned", "dispatched", "in_transit", "delivered"])
    async def test_create_rejects_legacy_operational_status(
        self, client, override_auth_tenant, legacy_status: str
    ) -> None:
        resp = await client.post(
            "/api/v1/loads",
            json={"status": legacy_status},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422

    async def test_create_draft_load_no_broker(self, client, override_auth_tenant) -> None:
        resp = await client.post(
            "/api/v1/loads",
            json={"status": "draft"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data.get("concurrency_version") == 1
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
        cv = cr.json()["concurrency_version"]

        up = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "A"},
                    {"stop_type": "PICKUP", "sequence": 1, "facility_name": "A2"},
                    {"stop_type": "DROP", "sequence": 2, "facility_name": "B"},
                ],
                "expected_concurrency_version": cv,
            },
            headers=AUTH_HEADERS,
        )
        assert up.status_code == 200
        data = up.json()
        assert len(data["stops"]) == 3
        names = [s["facility_name"] for s in sorted(data["stops"], key=lambda x: x["sequence"])]
        assert names == ["A", "A2", "B"]

    async def test_patch_stale_concurrency_version_returns_409(self, client, override_auth_tenant) -> None:
        cr = await client.post(
            "/api/v1/loads",
            json={"status": "draft", "load_number": f"L-CAS-409-{uuid.uuid4().hex[:8]}"},
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        cv0 = cr.json()["concurrency_version"]
        u1 = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"internal_notes": "first", "expected_concurrency_version": cv0},
            headers=AUTH_HEADERS,
        )
        assert u1.status_code == 200, u1.text
        stale = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"internal_notes": "second", "expected_concurrency_version": cv0},
            headers=AUTH_HEADERS,
        )
        assert stale.status_code == 409, stale.text
        detail = stale.json().get("detail")
        assert isinstance(detail, dict)
        assert detail.get("code") == "LOAD_VERSION_CONFLICT"


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
        cv = cr.json()["concurrency_version"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            json={"expected_concurrency_version": cv},
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
        cv = cr.json()["concurrency_version"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            json={"expected_concurrency_version": cv},
            headers=AUTH_HEADERS,
        )
        assert mr.status_code == 200
        body = mr.json()
        assert body["status"] == "ready"
        assert body.get("active_dispatch_trip_id") in (None, 0)
        assert body.get("active_trip_id") in (None, 0)

    async def test_mark_ready_success_with_delivery_stop(self, client, override_auth_tenant) -> None:
        """Default Load Page manual pair is PICKUP + DELIVERY; mark-ready must accept DELIVERY."""
        load_num = f"L-READY-DLV-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "broker_name_snapshot": "TQL",
                "broker_load_reference": "PO-DLV-1",
                "status": "draft",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "S"},
                    {"stop_type": "DELIVERY", "sequence": 1, "facility_name": "D"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        cv = cr.json()["concurrency_version"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            json={"expected_concurrency_version": cv},
            headers=AUTH_HEADERS,
        )
        assert mr.status_code == 200, mr.text
        body = mr.json()
        assert body["status"] == "ready"
        assert body.get("active_dispatch_trip_id") in (None, 0)
        assert body.get("active_trip_id") in (None, 0)

    async def test_mark_ready_rejects_non_draft(self, client, override_auth_tenant) -> None:
        load_num = f"L-READY-ND-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "broker_name_snapshot": "TQL",
                "broker_load_reference": "PO-ND",
                "status": "ready",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "S"},
                    {"stop_type": "DROP", "sequence": 1, "facility_name": "D"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        cv = cr.json()["concurrency_version"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            json={"expected_concurrency_version": cv},
            headers=AUTH_HEADERS,
        )
        assert mr.status_code == 400
        assert "draft" in mr.json().get("detail", "").lower()

    async def test_mark_ready_rejects_pickup_only(self, client, override_auth_tenant) -> None:
        load_num = f"L-READY-PO-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "broker_name_snapshot": "TQL",
                "broker_load_reference": "PO-PO",
                "status": "draft",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "S"},
                    {"stop_type": "PICKUP", "sequence": 1, "facility_name": "S2"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        cv = cr.json()["concurrency_version"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            json={"expected_concurrency_version": cv},
            headers=AUTH_HEADERS,
        )
        assert mr.status_code == 400
        detail = mr.json().get("detail", "").lower()
        assert "delivery" in detail or "drop" in detail

    async def test_mark_ready_rejects_missing_broker_load_reference(self, client, override_auth_tenant) -> None:
        load_num = f"L-READY-NOREF-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={
                "load_number": load_num,
                "broker_name_snapshot": "TQL",
                "broker_load_reference": None,
                "status": "draft",
                "stops": [
                    {"stop_type": "PICKUP", "sequence": 0, "facility_name": "S"},
                    {"stop_type": "DELIVERY", "sequence": 1, "facility_name": "D"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        cv = cr.json()["concurrency_version"]
        mr = await client.post(
            f"/api/v1/loads/{load_id}/mark-ready",
            json={"expected_concurrency_version": cv},
            headers=AUTH_HEADERS,
        )
        assert mr.status_code == 400
        assert "broker" in mr.json().get("detail", "").lower() and "reference" in mr.json().get("detail", "").lower()
