"""Load operational references: schema mapping, sanitization, PATCH presence, API persist."""
from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_TENANT_RESOLUTION_SHORTCUTS"] = "true"

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.load import LoadCreate, LoadResponse, LoadUpdate
from app.services.load_operational_references import sanitize_load_operational_references
from app.services.loads import _load_data_from_payload

REQUIRES_DB = not os.environ.get("DATABASE_URL")


def test_create_defaults_references_to_empty_collection() -> None:
    payload = LoadCreate(status="draft")
    assert payload.references == []
    data = _load_data_from_payload(payload)
    assert "references" not in data
    assert data["operational_references"] == []


def test_create_maps_references_to_operational_references() -> None:
    payload = LoadCreate(
        status="draft",
        references=[
            {
                "kind": "po_number",
                "value": "PO-1",
                "label": "PO #",
                "primary_candidate": False,
                "confidence": "high",
            }
        ],
    )
    data = _load_data_from_payload(payload)
    assert "references" not in data
    assert data["operational_references"] == [
        {
            "kind": "po_number",
            "value": "PO-1",
            "label": "PO #",
            "primary_candidate": False,
            "confidence": "high",
        }
    ]


def test_create_rejects_public_orm_field_name() -> None:
    with pytest.raises(ValidationError):
        LoadCreate(status="draft", operational_references=[{"kind": "po_number", "value": "x"}])


def test_sanitize_drops_empty_items() -> None:
    cleaned = sanitize_load_operational_references(
        [
            {"kind": "po_number", "value": "OK"},
            {"kind": "", "value": "x"},
            {"kind": "bol_number", "value": "   "},
            {"kind": "po_number"},
            "nope",
        ]
    )
    assert cleaned == [{"kind": "po_number", "value": "OK"}]


def test_create_sanitizes_empty_kind_items() -> None:
    payload = LoadCreate(
        status="draft",
        references=[
            {"kind": "", "value": "x"},
            {"kind": "po_number", "value": "OK"},
        ],
    )
    data = _load_data_from_payload(payload)
    assert data["operational_references"] == [{"kind": "po_number", "value": "OK"}]


def test_create_rejects_item_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        LoadCreate(status="draft", references=[{"kind": "po_number"}])


def test_patch_omission_does_not_include_operational_references() -> None:
    payload = LoadUpdate(expected_concurrency_version=1, status="draft")
    assert "references" not in payload.model_fields_set
    data = _load_data_from_payload(payload)
    assert "references" not in data
    assert "operational_references" not in data


def test_patch_empty_list_clears_collection() -> None:
    payload = LoadUpdate(expected_concurrency_version=1, references=[])
    assert "references" in payload.model_fields_set
    data = _load_data_from_payload(payload)
    assert data["operational_references"] == []


def test_patch_replacement_maps_collection() -> None:
    payload = LoadUpdate(
        expected_concurrency_version=1,
        references=[{"kind": "bol_number", "value": "BOL-2", "label": "BOL #"}],
    )
    data = _load_data_from_payload(payload)
    assert data["operational_references"] == [
        {"kind": "bol_number", "value": "BOL-2", "label": "BOL #"}
    ]


def test_patch_null_references_rejected() -> None:
    with pytest.raises(ValidationError):
        LoadUpdate(expected_concurrency_version=1, references=None)


def test_response_maps_operational_references_from_dict() -> None:
    resp = LoadResponse.model_validate(
        {
            "id": 1,
            "load_number": "INT-1",
            "status": "draft",
            "operational_references": [{"kind": "po_number", "value": "P1"}],
        }
    )
    dumped = resp.model_dump()
    assert dumped["references"] == [{"kind": "po_number", "value": "P1", "label": None, "primary_candidate": None, "confidence": None}]
    assert "operational_references" not in dumped


def test_response_from_orm_property() -> None:
    class _Row:
        id = 1
        load_number = "INT-1"
        status = "draft"
        concurrency_version = 1
        operational_references = [{"kind": "el_number", "value": "EL-1"}]
        broker_id = None
        broker_contact_id = None
        customs_broker_id = None
        driver_id = None
        truck_id = None
        trailer_id = None
        broker_name_snapshot = None
        broker_contact_name_snapshot = None
        broker_contact_phone_snapshot = None
        broker_contact_extension_snapshot = None
        broker_contact_email_snapshot = None
        broker_load_reference = None
        mode = None
        equipment_type = None
        trailer_type = None
        trailer_size = None
        commodity = None
        estimated_weight = None
        hazmat_flag = False
        temperature_requirement = None
        pallet_case_count = None
        internal_notes = None
        rate = None
        customer_rate = None
        miles = None
        trip_number = None
        active_dispatch_trip_id = None
        active_trip_id = None
        broker_match_method = None
        broker_match_confidence_tier = None
        broker_match_explanation = None
        review_required = False
        is_duplicate_of_load_id = None
        driver = None
        broker = None
        broker_contact = None
        customs_broker = None
        document_snapshot_confirmed_at = None
        document_snapshot_confirmed_by_user_id = None
        document_snapshot_version = 0
        customs_snapshot = None
        truck = None
        trailer = None
        stops = []
        created_at = None
        updated_at = None

        @property
        def references(self):
            val = self.operational_references
            return val if isinstance(val, list) else []

    resp = LoadResponse.model_validate(_Row())
    dumped = resp.model_dump()
    assert dumped["references"][0]["kind"] == "el_number"
    assert "operational_references" not in dumped


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestLoadOperationalReferencesApi:
    @pytest.fixture(autouse=True)
    def test_bypass_env(self):
        old = os.environ.get("TEST_BYPASS_AUTH")
        os.environ["TEST_BYPASS_AUTH"] = "1"
        yield
        if old is None:
            os.environ.pop("TEST_BYPASS_AUTH", None)
        else:
            os.environ["TEST_BYPASS_AUTH"] = old

    @pytest.fixture
    async def client(self):
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    @pytest.fixture
    def override_auth_tenant(self, test_bypass_env):
        from app.main import app
        from tests.support.integration_auth import (
            clear_current_user_and_tenant_overrides,
            install_host_aligned_current_user_and_tenant,
        )

        install_host_aligned_current_user_and_tenant(app)
        yield
        clear_current_user_and_tenant_overrides(app)

    async def test_create_get_patch_references_lifecycle(self, client, override_auth_tenant) -> None:
        headers = {"host": "demo.truckerp.me"}
        refs = [
            {"kind": "po_number", "value": "PO-KEEP", "label": "PO #", "confidence": "high"},
            {"kind": "pickup_number", "value": "PU-9"},
        ]
        cr = await client.post(
            "/api/v1/loads",
            json={
                "status": "draft",
                "load_number": f"L-REF-{uuid.uuid4().hex[:8]}",
                "references": refs,
            },
            headers=headers,
        )
        assert cr.status_code == 201, cr.text
        created = cr.json()
        assert "operational_references" not in created
        assert created["references"][0]["kind"] == "po_number"
        assert created["references"][0]["value"] == "PO-KEEP"
        load_id = created["id"]
        cv = created["concurrency_version"]

        got = await client.get(f"/api/v1/loads/{load_id}", headers=headers)
        assert got.status_code == 200
        assert got.json()["references"][0]["value"] == "PO-KEEP"

        omit = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"internal_notes": "leave refs", "expected_concurrency_version": cv},
            headers=headers,
        )
        assert omit.status_code == 200, omit.text
        assert omit.json()["references"][0]["value"] == "PO-KEEP"
        cv2 = omit.json()["concurrency_version"]

        replaced = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={
                "references": [{"kind": "bol_number", "value": "BOL-NEW"}],
                "expected_concurrency_version": cv2,
            },
            headers=headers,
        )
        assert replaced.status_code == 200, replaced.text
        assert [r["value"] for r in replaced.json()["references"]] == ["BOL-NEW"]
        cv3 = replaced.json()["concurrency_version"]

        cleared = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"references": [], "expected_concurrency_version": cv3},
            headers=headers,
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["references"] == []
