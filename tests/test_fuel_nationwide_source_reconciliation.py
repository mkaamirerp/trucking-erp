"""Nationwide source reconciliation — real fixture math locks."""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_nationwide_effective import build_effective_nationwide_rows
from app.services.fuel_nationwide_extraction import extract_nationwide_rows_from_digital_pdf
from app.services.fuel_nationwide_import import (
    NATIONWIDE_SOURCE_FIELD_NAMES,
    ROW_CONTROL,
    ROW_HEADER,
    ROW_TRANSACTION,
)
from app.services.fuel_nationwide_source_reconciliation import reconcile_nationwide_source_rows

REPO = Path(__file__).resolve().parents[1]
NW_PDF = REPO / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"


def _rows_from_pdf() -> list[dict]:
    extracted, _w, _v = extract_nationwide_rows_from_digital_pdf(NW_PDF.read_bytes())
    out: list[dict] = []
    for i, item in enumerate(extracted, start=1):
        row = {"id": i, "row_type": item.row_type}
        for k in NATIONWIDE_SOURCE_FIELD_NAMES:
            if k in item.fields:
                row[k] = item.fields[k]
        out.append(row)
    return build_effective_nationwide_rows(out)


def test_real_fixture_reconciliation_passes() -> None:
    result = reconcile_nationwide_source_rows(_rows_from_pdf())
    assert result.passed is True
    assert result.usd_row_total_sum == "5197.67"
    assert result.usd_precision_extension == "5197.69488"
    assert result.usd_provider_control == "5197.69"
    assert result.usd_precision_difference == "0.00"
    assert result.cad_ex_tax_control == "1118.45"
    assert result.cad_gst == "145.40"
    assert result.cad_pst == "0.00"
    assert result.cad_subtotal == "1263.85"

    card_controls = {
        (
            c["card_number"],
            c["currency"],
            c["declared_amount"],
        )
        for c in result.card_controls
    }

    assert ("XXXXX07588", "USD", "722.75") in card_controls
    assert ("XXXXX87195", "CAD", "1263.85") in card_controls


def test_usd_quantity_tamper_fails() -> None:
    rows = copy.deepcopy(_rows_from_pdf())
    txn = next(r for r in rows if r.get("row_type") == ROW_TRANSACTION and r.get("currency") == "USD")
    txn["volume"] = "999"
    result = reconcile_nationwide_source_rows(rows)
    assert result.passed is False


def test_usd_billing_control_tamper_fails() -> None:
    rows = copy.deepcopy(_rows_from_pdf())
    ctl = next(r for r in rows if r.get("row_label") == "USD_BILLING_TOTAL")
    ctl["declared_amount"] = "1.00"
    result = reconcile_nationwide_source_rows(rows)
    assert result.passed is False

def test_usd_only_document_does_not_require_cad_controls() -> None:
    rows = [
        {
            "row_type": ROW_HEADER,
            "invoice_number": "USD-ONLY",
        },
        {
            "row_type": ROW_TRANSACTION,
            "currency": "USD",
            "volume": "10.00",
            "ex_gst_per_unit": "2.00",
            "total": "20.00",
            "card_number": "XXXXX1",
        },
        {
            "row_type": ROW_CONTROL,
            "control_type": "CURRENCY_TOTAL",
            "row_label": "USD_BILLING_TOTAL",
            "declared_amount": "20.00",
            "currency": "USD",
            "control_line_raw": "USD billing total $20.00",
        },
    ]

    result = reconcile_nationwide_source_rows(rows)

    assert result.passed is True
    assert result.usd_provider_control == "20.00"
    assert result.cad_ex_tax_control is None
    assert not any(
        c.code == "CAD_EX_TAX_CONTROL_MISSING"
        for c in result.checks
    )


def test_cad_only_document_does_not_require_usd_control() -> None:
    rows = [
        {
            "row_type": ROW_HEADER,
            "invoice_number": "CAD-ONLY",
        },
        {
            "row_type": ROW_TRANSACTION,
            "currency": "CAD",
            "volume": "10.00",
            "ex_gst_per_unit": "2.00",
            "total": "22.60",
        },
        {
            "row_type": ROW_CONTROL,
            "control_type": "INVOICE_SUMMARY",
            "control_line_raw": "Total Ex-GST & PST $20.00",
        },
        {
            "row_type": ROW_CONTROL,
            "control_type": "TAX_CONTROL",
            "control_line_raw": "GST $2.60",
        },
        {
            "row_type": ROW_CONTROL,
            "control_type": "TAX_CONTROL",
            "control_line_raw": "PST $0.00",
        },
        {
            "row_type": ROW_CONTROL,
            "control_type": "PROVIDER_DECLARED_TOTAL",
            "control_line_raw": "Subtotal $22.60",
        },
    ]

    result = reconcile_nationwide_source_rows(rows)

    assert result.passed is True
    assert result.usd_provider_control is None
    assert result.cad_ex_tax_control == "20.00"
    assert result.cad_gst == "2.60"
    assert result.cad_pst == "0.00"
    assert result.cad_subtotal == "22.60"
    assert not any(
        c.code == "USD_BILLING_CONTROL_MISSING"
        for c in result.checks
    )


def test_document_without_transactions_fails() -> None:
    rows = [
        {
            "row_type": ROW_HEADER,
            "invoice_number": "EMPTY",
        }
    ]

    result = reconcile_nationwide_source_rows(rows)

    assert result.passed is False
    assert any(
        c.code == "NO_TRANSACTIONS"
        and c.status == "FAIL"
        for c in result.checks
    )
