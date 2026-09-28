"""BVD Express — field hydration from parse through API response (no parser/recon changes)."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.fuel import FuelBvdRowOut
from app.services.fuel_bvd_extraction import ROW_EXPRESS_TRANSACTION, extract_bvd_rows_from_digital_pdf
from app.services.fuel_bvd_import import BVD_SOURCE_FIELD_NAMES, fuel_bvd_row_to_dict
from app.services.fuel_bvd_stage import _apply_fields_to_stage_row, stage_row_to_dict

REPO = Path(__file__).resolve().parents[1]
BVD_838710 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_838710.pdf"

EXPECTED_TRACTORS = [
    "1111",
    "1103",
    "1103",
    "1111",
    "1103",
    "1110",
    "1111",
    "1111",
    "1111",
    "1110",
    None,
]


def _express_row(rows, express_code: str):
    for row in rows:
        if row.row_type != ROW_EXPRESS_TRANSACTION:
            continue
        if row.fields.get("express_code") == express_code:
            return row.fields
    raise AssertionError(f"express row not found: {express_code}")


@pytest.mark.skipif(not BVD_838710.is_file(), reason="BVD_invoice_838710.pdf fixture not present")
def test_express_5359948_fields_after_parse() -> None:
    rows, _, _ = extract_bvd_rows_from_digital_pdf(BVD_838710.read_bytes())
    fields = _express_row(rows, "5359948")
    assert fields["express_tractor"] == "1103"
    assert fields["driver_name"] == "Nathnel"
    assert fields["auth_code"] == "E345296820"
    assert fields["amount_cashed"] == "200"
    assert fields["express_fee"] == "3"
    assert fields["final_amt"] == "203"
    assert fields["cur"] == "US"
    assert fields["payee_raw"] == "lumper fee"


@pytest.mark.skipif(not BVD_838710.is_file(), reason="BVD_invoice_838710.pdf fixture not present")
def test_express_838710_tractor_sequence_and_codes() -> None:
    rows, _, _ = extract_bvd_rows_from_digital_pdf(BVD_838710.read_bytes())
    express = [r for r in rows if r.row_type == ROW_EXPRESS_TRANSACTION]
    assert len(express) == 11
    assert [r.fields.get("express_tractor") for r in express] == EXPECTED_TRACTORS
    assert [r.fields.get("express_code") for r in express[:3]] == ["5356662", "5357926", "5359948"]


def test_fuel_bvd_row_out_includes_express_columns() -> None:
    """Regression: API response_model must not drop express source columns."""
    payload = {
        "id": 99,
        "import_id": str(uuid.uuid4()),
        "row_type": "EXPRESS_TRANSACTION",
        "transaction_date": "2025-12-11 08:14:42",
        "express_code": "5359948",
        "auth_code": "E345296820",
        "express_tractor": "1103",
        "driver_name": "Nathnel",
        "amount_cashed": "200.00",
        "express_fee": "3.00",
        "final_amt": "203.00",
        "cur": "US",
        "payee_raw": "lumper fee",
    }
    out = FuelBvdRowOut(**payload)
    assert out.express_code == "5359948"
    assert out.express_tractor == "1103"
    assert out.amount_cashed == "200.00"
    assert out.express_fee == "3.00"
    assert out.cur == "US"
    assert out.payee_raw == "lumper fee"


def test_stage_row_dict_and_permanent_serialization_survive_express_fields() -> None:
    """Stage persistence + fuel_bvd_row_to_dict + FuelBvdRowOut (Process path shape)."""
    fields = {
        "transaction_date": "2025-12-11 08:14:42",
        "express_code": "5359948",
        "auth_code": "E345296820",
        "express_tractor": "1103",
        "driver_name": "Nathnel",
        "amount_cashed": "200.00",
        "express_fee": "3.00",
        "final_amt": "203.00",
        "cur": "US",
        "payee_raw": "lumper fee",
    }
    stage_id = uuid.uuid4()
    stage_row = SimpleNamespace(
        id=42,
        row_type="EXPRESS_TRANSACTION",
        source_page=3,
        source_row_number=50,
        **{name: None for name in BVD_SOURCE_FIELD_NAMES},
    )
    _apply_fields_to_stage_row(stage_row, fields)
    stage = SimpleNamespace(
        stage_id=stage_id,
        source_file_name="BVD.pdf",
        source_file_sha256="abc",
        source_storage_ref="key",
        parse_status="SUCCESS",
        parser_version="BVD:1",
        extraction_warnings=None,
    )
    staged_api = stage_row_to_dict(stage_row, stage)
    assert staged_api["express_code"] == "5359948"
    assert staged_api["express_tractor"] == "1103"
    assert staged_api["amount_cashed"] == "200.00"
    assert staged_api["cur"] == "US"

    permanent = SimpleNamespace(
        id=1001,
        import_id=stage_id,
        row_type="EXPRESS_TRANSACTION",
        source_file_name=stage.source_file_name,
        source_file_sha256=stage.source_file_sha256,
        source_storage_ref="perm/key",
        source_page=stage_row.source_page,
        source_row_number=stage_row.source_row_number,
        parse_status=stage.parse_status,
        parser_version=stage.parser_version,
        extraction_warnings=None,
        **{name: getattr(stage_row, name) for name in BVD_SOURCE_FIELD_NAMES},
    )
    permanent_dict = fuel_bvd_row_to_dict(permanent)
    api_row = FuelBvdRowOut(**permanent_dict)
    assert api_row.express_code == "5359948"
    assert api_row.express_tractor == "1103"
    assert api_row.driver_name == "Nathnel"
    assert api_row.amount_cashed == "200.00"
    assert api_row.express_fee == "3.00"
    assert api_row.final_amt == "203.00"
    assert api_row.cur == "US"
    assert api_row.payee_raw == "lumper fee"
