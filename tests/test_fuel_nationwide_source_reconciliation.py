"""Nationwide source reconciliation — real fixture math locks."""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_nationwide_effective import build_effective_nationwide_rows
from app.services.fuel_nationwide_extraction import extract_nationwide_rows_from_digital_pdf
from app.services.fuel_nationwide_import import NATIONWIDE_SOURCE_FIELD_NAMES, ROW_TRANSACTION
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
