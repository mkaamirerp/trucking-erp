"""BVD parser regression — complex invoice 838710 (column geometry / multi-section)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_bvd_extraction import FuelBvdExtractionError, extract_bvd_rows_from_digital_pdf
from app.services.fuel_bvd_extraction import (
    ROW_EXPRESS_SUBTOTAL,
    ROW_EXPRESS_TRANSACTION,
    ROW_TRANSACTION,
)
from app.services.fuel_bvd_source_reconciliation import parse_bvd_decimal, reconcile_bvd_source_rows

REPO = Path(__file__).resolve().parents[1]
BVD_838710 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_838710.pdf"


def _txn(rows, auth_code: str) -> dict:
    for row in rows:
        if row.row_type != ROW_TRANSACTION:
            continue
        if row.fields.get("auth_code") == auth_code:
            return row.fields
    raise AssertionError(f"transaction not found: {auth_code}")


def _rows_as_dicts(rows) -> list[dict]:
    return [{"id": i + 1, "import_id": "838710", "row_type": r.row_type, **r.fields} for i, r in enumerate(rows)]


def _sum_final(rows, row_type: str) -> Decimal:
    total = Decimal("0")
    for r in rows:
        if r.row_type != row_type:
            continue
        dec, _ = parse_bvd_decimal(r.fields.get("final_amt"))
        total += dec or Decimal("0")
    return total


@pytest.mark.skipif(not BVD_838710.is_file(), reason="BVD_invoice_838710.pdf fixture not present")
def test_bvd_838710_transaction_site_columns_from_geometry() -> None:
    rows, _warnings, _pv = extract_bvd_rows_from_digital_pdf(BVD_838710.read_bytes())
    assert not any(
        "cannot split Site Name / Site City without column boundaries" in str(r)
        for r in rows
    )

    t1 = _txn(rows, "A344082616-TA")
    assert t1["driver_name"] == "GURPREET SINGH"
    assert t1["unit_number"] == "1129"
    assert t1["site_number"] == "33078"
    assert t1["site_name"] == "LOVES #412"
    assert t1["site_city"] == "Dunn"
    assert t1["prov_st"] == "NC"
    assert t1["prod"] == "TA"
    assert t1["qty"] == "50.14"
    assert t1["final_amt"] == "155.77"
    assert t1["cur"] == "US"

    t2 = _txn(rows, "A344532758-TA")
    assert t2["driver_name"] == "ROBEL"
    assert t2["unit_number"] == "7186"
    assert t2["site_number"] == "50479"
    assert t2["site_name"] == "LOVES #829"
    assert t2["site_city"] == "Brookville"
    assert t2["prov_st"] == "PA"


@pytest.mark.skipif(not BVD_838710.is_file(), reason="BVD_invoice_838710.pdf fixture not present")
def test_bvd_838710_purchase_and_express_counts_and_totals() -> None:
    try:
        rows, warnings, parser_version = extract_bvd_rows_from_digital_pdf(BVD_838710.read_bytes())
    except FuelBvdExtractionError as exc:
        pytest.fail(f"838710 parse failed: {exc.code}: {exc.message}")

    purchases = [r for r in rows if r.row_type == ROW_TRANSACTION]
    express = [r for r in rows if r.row_type == ROW_EXPRESS_TRANSACTION]
    express_sub = [r for r in rows if r.row_type == ROW_EXPRESS_SUBTOTAL]

    assert len(purchases) == 31
    assert len(express) == 11
    assert len(express_sub) == 1

    s1107 = [_txn(rows, c) for c in ("A350330291-TA", "A350330291-TF", "A350330291-DF")]
    assert s1107[0]["unit_number"] == "S1107"
    s1107_sum = sum(parse_bvd_decimal(t["final_amt"])[0] or 0 for t in s1107)
    assert s1107_sum == Decimal("654.73")

    scale = [_txn(rows, c) for c in ("A345807361-S", "A347408986-S", "A347627083-S")]
    assert sum(parse_bvd_decimal(t["final_amt"])[0] or 0 for t in scale) == Decimal("44.25")

    purchase_total = _sum_final(rows, ROW_TRANSACTION)
    assert purchase_total == Decimal("7370.94")

    cashed = sum(parse_bvd_decimal(r.fields.get("amount_cashed"))[0] or 0 for r in express)
    fees = sum(parse_bvd_decimal(r.fields.get("express_fee"))[0] or 0 for r in express)
    express_total = _sum_final(rows, ROW_EXPRESS_TRANSACTION)
    assert cashed == Decimal("1643.78")
    assert fees == Decimal("33.00")
    assert express_total == Decimal("1676.78")

    assert express_sub[0].fields.get("final_amt") == "1676.78"

    toll_row = next(r for r in express if r.fields.get("auth_code") == "E347439580")
    assert toll_row.fields.get("express_tractor") in (None, "")
    assert toll_row.fields.get("payee_raw") == "toll pay"

    recon = reconcile_bvd_source_rows(_rows_as_dicts(rows))
    assert recon.passed is True
    assert recon.difference == "0.00"
    assert recon.provider_grand_total == "9047.72"
    assert recon.transaction_total == "7370.94"

    assert parser_version.startswith("BVD:")
    assert isinstance(warnings, list)
