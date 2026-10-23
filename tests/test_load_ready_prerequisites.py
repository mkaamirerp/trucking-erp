"""Unit tests for shared mark-ready / promote prerequisites (no DB)."""

from app.schemas.load import LoadCreate, LoadStopCreate
from app.services.loads import validate_load_ready_prerequisites_from_create


def test_validate_load_ready_prerequisites_from_create_ok() -> None:
    payload = LoadCreate(
        status="draft",
        broker_name_snapshot="Acme",
        broker_load_reference="REF-1",
        stops=[
            LoadStopCreate(stop_type="PICKUP", sequence=0, city="A", state_or_province="ON"),
            LoadStopCreate(stop_type="DELIVERY", sequence=1, city="B", state_or_province="QC"),
        ],
    )
    assert validate_load_ready_prerequisites_from_create(payload) == []


def test_validate_load_ready_prerequisites_from_create_missing_ref() -> None:
    payload = LoadCreate(
        status="draft",
        broker_name_snapshot="Acme",
        stops=[
            LoadStopCreate(stop_type="PICKUP", sequence=0),
            LoadStopCreate(stop_type="DELIVERY", sequence=1),
        ],
    )
    missing = validate_load_ready_prerequisites_from_create(payload)
    assert "Load # / PO # is required" in missing


def test_validate_load_ready_prerequisites_from_create_load_number_only() -> None:
    payload = LoadCreate(
        status="draft",
        broker_name_snapshot="Acme",
        load_number="L-9001",
        stops=[
            LoadStopCreate(stop_type="PICKUP", sequence=0, city="A", state_or_province="ON"),
            LoadStopCreate(stop_type="DELIVERY", sequence=1, city="B", state_or_province="QC"),
        ],
    )
    assert validate_load_ready_prerequisites_from_create(payload) == []
