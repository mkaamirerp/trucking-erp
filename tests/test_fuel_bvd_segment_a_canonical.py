"""Segment A: BVD → fuel_transactions + fuel_source_controls projection."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_bvd_canonical_projection import (
    MONEY_ROW_TYPES,
    SECTION_EXPRESS,
    SECTION_FUEL_CARD,
    assert_canonical_money_gate,
    build_fuel_source_batch,
    project_bvd_rows_to_canonical,
)
from app.services.fuel_bvd_effective import build_effective_bvd_row
from app.services.fuel_bvd_extraction import (
    ROW_EXPRESS_TRANSACTION,
    ROW_GRAND_TOTAL,
    ROW_HEADER,
    ROW_TRANSACTION,
    extract_bvd_rows_from_digital_pdf,
)
from app.services.fuel_bvd_source_reconciliation import parse_bvd_decimal, reconcile_bvd_source_rows
from app.services.fuel_controls import CONTROL_TYPE_CARD_TOTAL, CONTROL_TYPE_INVOICE_TOTAL

REPO = Path(__file__).resolve().parents[1]
BVD_838710 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_838710.pdf"
BVD_972201 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"

EXPECTED_CARDS_838710 = {
    "4236501",
    "4236576",
    "4236675",
    "4236980",
    "4237061",
    "4237160",
    "4237186",
}


def _as_review_rows(extracted, import_id: str) -> tuple[list[dict], list[dict]]:
    raw_rows: list[dict] = []
    for i, row in enumerate(extracted):
        raw_rows.append(
            {
                "id": i + 1,
                "import_id": import_id,
                "row_type": row.row_type,
                "source_page": row.source_page,
                "source_row_number": i + 1,
                **row.fields,
            }
        )
    effective_rows = [build_effective_bvd_row(r) for r in raw_rows]
    return raw_rows, effective_rows


def _project_fixture(pdf_path: Path) -> tuple[list, list, list]:
    extracted, _, _ = extract_bvd_rows_from_digital_pdf(pdf_path.read_bytes())
    import_id = str(uuid.uuid4())
    raw_rows, effective_rows = _as_review_rows(extracted, import_id)
    id_map = {int(r["id"]): 1000 + int(r["id"]) for r in raw_rows}
    header = next(r for r in raw_rows if r["row_type"] == ROW_HEADER)
    batch = build_fuel_source_batch(
        tenant_id=53,
        import_id=uuid.UUID(import_id),
        header=header,
        source_hash="sha",
        source_storage_ref="key",
        parser_version="BVD:test",
        reviewed_by="pytest",
    )
    batch.id = 1
    txns, controls = project_bvd_rows_to_canonical(
        tenant_id=53,
        batch=batch,
        import_id=uuid.UUID(import_id),
        raw_rows=raw_rows,
        effective_rows=effective_rows,
        fuel_bvd_id_by_stage_row_id=id_map,
    )
    return txns, controls, raw_rows


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_bvd_838710_canonical_42_rows_and_total() -> None:
    txns, controls, raw_rows = _project_fixture(BVD_838710)
    purchases = [t for t in txns if t.provider_section_raw == SECTION_FUEL_CARD]
    express = [t for t in txns if t.provider_section_raw == SECTION_EXPRESS]
    assert len(purchases) == 31
    assert len(express) == 11
    assert len(txns) == 42
    total = sum((t.total_amount or Decimal("0") for t in txns), Decimal("0"))
    assert total == Decimal("9047.72")
    assert_canonical_money_gate(txns, controls, expected_transaction_count=42, expected_total=Decimal("9047.72"))


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_bvd_838710_express_canonical_row_e345296820() -> None:
    txns, _, _ = _project_fixture(BVD_838710)
    row = next(t for t in txns if t.provider_transaction_identity == "E345296820")
    assert row.provider_reference_raw == "5359948"
    assert row.unit_number_snapshot == "1103"
    assert row.driver_name_snapshot == "Nathnel"
    assert row.principal_amount == Decimal("200")
    assert row.provider_fee_amount == Decimal("3")
    assert row.total_amount == Decimal("203")
    assert row.currency_raw == "US"
    assert row.provider_reason_raw == "lumper fee"
    assert row.provider_section_raw == SECTION_EXPRESS
    assert row.card_or_account_id is None
    assert "payee_raw" in row.provider_raw["fields"]


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_bvd_838710_multi_card_on_purchases() -> None:
    txns, _, _ = _project_fixture(BVD_838710)
    cards = {t.card_or_account_id for t in txns if t.provider_section_raw == SECTION_FUEL_CARD}
    assert cards == EXPECTED_CARDS_838710


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_bvd_838710_card_subtotal_control_not_fuel_total() -> None:
    txns, controls, _ = _project_fixture(BVD_838710)
    card_totals = [c for c in controls if c.control_type == CONTROL_TYPE_CARD_TOTAL]
    assert card_totals
    assert any(c.scope_card_or_account_id == "4237061" for c in card_totals)
    sub_4237061 = next(
        c for c in card_totals if c.scope_card_or_account_id == "4237061" and c.declared_amount == Decimal("392.69")
    )
    assert sub_4237061 is not None
    fuel_totals = [c for c in controls if c.control_label_raw == "Fuel Total"]
    assert fuel_totals
    assert all(c.control_type != CONTROL_TYPE_CARD_TOTAL for c in fuel_totals)


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_bvd_838710_express_subtotal_is_control_not_transaction() -> None:
    txns, controls, _ = _project_fixture(BVD_838710)
    assert not any(t.provider_section_raw == SECTION_EXPRESS and t.total_amount == Decimal("1676.78") for t in txns)
    express_sub = [c for c in controls if c.control_label_raw == "EXPRESS SUBTOTAL"]
    assert len(express_sub) == 1
    assert express_sub[0].declared_amount == Decimal("1676.78")


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_effective_correction_changes_canonical_not_raw_provider() -> None:
    extracted, _, _ = extract_bvd_rows_from_digital_pdf(BVD_838710.read_bytes())
    import_id = str(uuid.uuid4())
    raw_rows, effective_rows = _as_review_rows(extracted, import_id)
    target = next(r for r in raw_rows if r.get("auth_code") == "A350330291-DF")
    target["field_corrections"] = {
        "prod": {
            "field_name": "prod",
            "extracted_value": "DF",
            "reviewed_value": "S",
        }
    }
    effective_rows = [build_effective_bvd_row(r) for r in raw_rows]
    eff = next(r for r in effective_rows if r.get("auth_code") == "A350330291-DF")
    assert eff["prod"] == "S"
    assert target["prod"] == "DF"
    id_map = {int(r["id"]): 1000 + int(r["id"]) for r in raw_rows}
    header = next(r for r in raw_rows if r["row_type"] == ROW_HEADER)
    batch = build_fuel_source_batch(
        tenant_id=53,
        import_id=uuid.UUID(import_id),
        header=header,
        source_hash="sha",
        source_storage_ref="key",
        parser_version="BVD:test",
        reviewed_by="pytest",
    )
    batch.id = 1
    txns, _ = project_bvd_rows_to_canonical(
        tenant_id=53,
        batch=batch,
        import_id=uuid.UUID(import_id),
        raw_rows=raw_rows,
        effective_rows=effective_rows,
        fuel_bvd_id_by_stage_row_id=id_map,
    )
    txn = next(t for t in txns if t.provider_transaction_identity == "A350330291-DF")
    assert txn.product_code_raw == "S"
    assert txn.provider_raw["fields"]["prod"] == "DF"


@pytest.mark.skipif(not BVD_972201.is_file(), reason="972201 fixture missing")
def test_bvd_972201_canonical_two_rows() -> None:
    txns, controls, _ = _project_fixture(BVD_972201)
    assert len(txns) == 2
    total = sum((t.total_amount or Decimal("0") for t in txns), Decimal("0"))
    assert total == Decimal("3421.01")
    assert_canonical_money_gate(txns, controls, expected_transaction_count=2, expected_total=Decimal("3421.01"))


def test_line_arithmetic_variance_is_info_not_fail() -> None:
    rows = [
        {
            "id": 1,
            "import_id": "x",
            "row_type": ROW_TRANSACTION,
            "auth_code": "A1-TA",
            "unit_number": "1",
            "prod": "TA",
            "pre_tax_amt": "10.00",
            "hst": "0.00",
            "gst": "0.00",
            "pst": "0.00",
            "qst": "0.00",
            "disc_amt": "0.00",
            "final_amt": "10.02",
            "cur": "US",
        },
        {
            "id": 2,
            "import_id": "x",
            "row_type": ROW_GRAND_TOTAL,
            "row_label": "Grand Total",
            "final_amount": "10.02",
        },
    ]
    result = reconcile_bvd_source_rows(rows)
    line_checks = [c for c in result.checks if c.code.startswith("TXN_LINE_ARITHMETIC_")]
    assert line_checks
    assert all(c.status in {"PASS", "INFO"} for c in line_checks)
    assert result.passed is True


def test_authoritative_invoice_mismatch_fails() -> None:
    rows = [
        {
            "id": 1,
            "import_id": "x",
            "row_type": ROW_TRANSACTION,
            "auth_code": "A1-TA",
            "unit_number": "1",
            "prod": "TA",
            "final_amt": "10.00",
            "cur": "US",
        },
        {
            "id": 2,
            "import_id": "x",
            "row_type": ROW_GRAND_TOTAL,
            "row_label": "Grand Total",
            "final_amount": "10.01",
        },
    ]
    result = reconcile_bvd_source_rows(rows)
    assert result.passed is False
