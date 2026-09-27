"""BVD source reconciliation — Decimal money, no UI."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_bvd_source_reconciliation import (
    UNASSIGNED_UNIT_KEY,
    reconcile_bvd_source_rows,
)

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "fixtures" / "fuel_bvd_972201_expected.json"


def _golden_rows() -> list[dict]:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return [
        {"id": i + 1, "import_id": "test-import", **row}
        for i, row in enumerate(payload["rows"])
    ]


def _find(rows: list[dict], **kwargs: object) -> dict:
    for row in rows:
        if all(row.get(k) == v for k, v in kwargs.items()):
            return row
    raise AssertionError(f"row not found: {kwargs}")


def test_a_invoice_972201_happy_path() -> None:
    result = reconcile_bvd_source_rows(_golden_rows())
    assert result.passed is True
    assert result.transaction_total == "3421.01"
    assert result.all_unit_total == "3421.01"
    assert result.provider_grand_total == "3421.01"
    assert result.difference == "0.00"

    assert result.units["1100"]["final_amt"] == "1610.96"
    assert result.units["1104"]["final_amt"] == "1810.05"

    ta = result.products["TA"]
    assert ta["qty"] == "1474.00"
    assert ta["pre_tax_amt"] == "3027.44"
    assert ta["hst"] == "393.57"
    assert ta["final_amt"] == "3421.01"

    assert not any(c.status == "FAIL" for c in result.checks)


def test_b_one_cent_final_mismatch_fails() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A204040667-TA")
    txn["final_amt"] = "1,610.95"
    result = reconcile_bvd_source_rows(rows)
    assert result.passed is False
    assert result.difference == "0.01"
    assert any(c.status == "FAIL" and "GRAND_TOTAL" in c.code for c in result.checks)


def test_c_blank_unit_moves_unassigned_and_fails() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A208448597-TA")
    txn["unit_number"] = ""
    result = reconcile_bvd_source_rows(rows)
    assert result.passed is False
    assert UNASSIGNED_UNIT_KEY in result.units
    assert any(c.code == "MISSING_UNIT_NONZERO_FINAL" and c.status == "FAIL" for c in result.checks)


def test_d_unit_1100_includes_df_when_matching_provider_total() -> None:
    rows = copy.deepcopy(_golden_rows())
    max_id = max(r["id"] for r in rows)
    rows.append(
        {
            "id": max_id + 1,
            "import_id": "test-import",
            "row_type": "TRANSACTION",
            "unit_number": "1100",
            "prod": "DF",
            "qty": "10.00",
            "pre_tax_amt": "44.25",
            "hst": "5.75",
            "gst": "0.00",
            "pst": "0.00",
            "qst": "0.00",
            "disc_amt": "0.00",
            "final_amt": "50.00",
            "cur": "CN",
        }
    )
    df_grand = _find(rows, row_type="GRAND_TOTAL", row_label="DF")
    df_grand["qty"] = "10.00"
    df_grand["pre_tax_amt"] = "44.25"
    df_grand["hst"] = "5.75"
    df_grand["final_amount"] = "50.00"

    grand = _find(rows, row_type="GRAND_TOTAL", row_label="Grand Total")
    grand["qty"] = "1484.00"
    grand["pre_tax_amt"] = "3071.69"
    grand["hst"] = "399.32"
    grand["final_amount"] = "3,471.01"

    fuel_total = _find(rows, row_type="PAGE1_SUMMARY", row_label="Fuel Total")
    fuel_total["final_amt"] = "3,471.01"
    sub_total = _find(rows, row_type="PAGE1_SUMMARY", row_label="Sub Total")
    sub_total["final_amt"] = "3,471.01"

    result = reconcile_bvd_source_rows(rows)
    assert result.passed is True
    assert result.units["1100"]["final_amt"] == "1660.96"
    assert result.products["DF"]["final_amt"] == "50.00"


def test_e_scale_and_cash_included_in_unit_1100() -> None:
    rows = copy.deepcopy(_golden_rows())
    max_id = max(r["id"] for r in rows)
    rows.extend(
        [
            {
                "id": max_id + 1,
                "import_id": "test-import",
                "row_type": "TRANSACTION",
                "unit_number": "1100",
                "prod": "S",
                "final_amt": "20.00",
                "pre_tax_amt": "17.70",
                "hst": "2.30",
                "gst": "0.00",
                "pst": "0.00",
                "qst": "0.00",
                "disc_amt": "0.00",
                "qty": "1.00",
                "cur": "CN",
            },
            {
                "id": max_id + 2,
                "import_id": "test-import",
                "row_type": "TRANSACTION",
                "unit_number": "1100",
                "prod": "C",
                "final_amt": "100.00",
                "pre_tax_amt": "88.50",
                "hst": "11.50",
                "gst": "0.00",
                "pst": "0.00",
                "qst": "0.00",
                "disc_amt": "0.00",
                "qty": "1.00",
                "cur": "CN",
            },
        ]
    )
    max_id = max(r["id"] for r in rows)
    for i, (label, amt, pre, hst) in enumerate(
        (
            ("S", "20.00", "17.70", "2.30"),
            ("C", "100.00", "88.50", "11.50"),
        ),
        start=1,
    ):
        rows.append(
            {
                "id": max_id + i,
                "import_id": "test-import",
                "row_type": "GRAND_TOTAL",
                "row_label": label,
                "product": label,
                "final_amount": amt,
                "pre_tax_amt": pre,
                "hst": hst,
                "qty": "1.00",
                "gst": "0.00",
                "pst": "0.00",
                "qst": "0.00",
                "disc_amt": "0.00",
                "cur": "CN",
            }
        )

    grand = _find(rows, row_type="GRAND_TOTAL", row_label="Grand Total")
    grand["final_amount"] = "3,541.01"
    grand["pre_tax_amt"] = "3133.64"
    grand["hst"] = "407.37"
    grand["qty"] = "1476.00"

    fuel_total = _find(rows, row_type="PAGE1_SUMMARY", row_label="Fuel Total")
    fuel_total["final_amt"] = "3,541.01"
    sub_total = _find(rows, row_type="PAGE1_SUMMARY", row_label="Sub Total")
    sub_total["final_amt"] = "3,541.01"

    result = reconcile_bvd_source_rows(rows)
    assert result.passed is True
    assert result.units["1100"]["final_amt"] == "1730.96"
    assert result.products["S"]["final_amt"] == "20.00"
    assert result.products["C"]["final_amt"] == "100.00"


def test_f_unknown_product_code_not_dropped() -> None:
    rows = copy.deepcopy(_golden_rows())
    max_id = max(r["id"] for r in rows)
    rows.append(
        {
            "id": max_id + 1,
            "import_id": "test-import",
            "row_type": "TRANSACTION",
            "unit_number": "1100",
            "prod": "XX",
            "final_amt": "25.00",
            "pre_tax_amt": "22.12",
            "hst": "2.88",
            "gst": "0.00",
            "pst": "0.00",
            "qst": "0.00",
            "disc_amt": "0.00",
            "qty": "1.00",
            "cur": "CN",
        }
    )
    result = reconcile_bvd_source_rows(rows)
    assert "XX" in result.products
    assert result.products["XX"]["final_amt"] == "25.00"
    assert result.passed is False  # provider has no XX row / grand total not updated


def test_g_zero_manual_express_neutral() -> None:
    result = reconcile_bvd_source_rows(_golden_rows())
    manual = next(c for c in result.checks if c.code == "PROVIDER_MANUAL_ZERO")
    express = next(c for c in result.checks if c.code == "PROVIDER_EXPRESS_ZERO")
    assert manual.status == "PASS"
    assert express.status == "PASS"


def test_h_nonzero_manual_blocks() -> None:
    rows = copy.deepcopy(_golden_rows())
    manual = _find(rows, row_type="GRAND_TOTAL", row_label="Manual")
    manual["final_amount"] = "10.00"
    result = reconcile_bvd_source_rows(rows)
    assert result.passed is False
    assert any(c.code == "PROVIDER_MANUAL_UNRESOLVED" for c in result.checks)


def test_i_product_qty_mismatch_fails_even_if_final_matches() -> None:
    rows = copy.deepcopy(_golden_rows())
    ta = _find(rows, row_type="GRAND_TOTAL", row_label="TA")
    ta["qty"] = "1,475.00"
    result = reconcile_bvd_source_rows(rows)
    assert result.passed is False
    assert any(c.code == "PRODUCT_TA_QTY" and c.status == "FAIL" for c in result.checks)


def test_j_tax_subtotal_mismatch_fails() -> None:
    rows = copy.deepcopy(_golden_rows())
    ta = _find(rows, row_type="GRAND_TOTAL", row_label="TA")
    ta["hst"] = "393.58"
    result = reconcile_bvd_source_rows(rows)
    assert result.passed is False
    assert any(c.code == "PRODUCT_TA_HST" and c.status == "FAIL" for c in result.checks)


def test_k_currency_mismatch_fails() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A204040667-TA")
    txn["cur"] = "US"
    result = reconcile_bvd_source_rows(rows)
    assert result.passed is False
    assert any(c.code == "CURRENCY_MULTIPLE_WITHOUT_SPLIT" for c in result.checks)


def test_decimal_exact_cent_no_float_tolerance() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A204040667-TA")
    txn["final_amt"] = "1,610.95"
    result = reconcile_bvd_source_rows(rows)
    fail = next(c for c in result.checks if c.code == "CORE_TXN_TOTAL_VS_PROVIDER_GRAND")
    assert fail.difference == "0.01"
    assert Decimal(fail.difference) == Decimal("0.01")
