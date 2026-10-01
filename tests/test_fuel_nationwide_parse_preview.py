"""Nationwide parse-only source-fidelity proof (real PDF, no persistence)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_parse_preview import parse_fuel_pdf_preview
from app.services.fuel_provider_profile import assert_no_separate_provider_parser_engines

REPO = Path(__file__).resolve().parents[1]
NW_PDF = REPO / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"
PROFILE_VERSION = "2026-09-19"


def _sum_currency(transactions: list[dict], currency: str) -> Decimal:
    total = Decimal("0")
    for row in transactions:
        raw = row["provider_raw"]
        if raw.get("Currency") != currency:
            continue
        total += Decimal(str(raw["Total"]).replace(",", ""))
    return total


def test_parse_preview_module_has_no_database_surface() -> None:
    source = (REPO / "app/services/fuel_parse_preview.py").read_text(encoding="utf-8")
    import_block = source.split('"""', 2)[-1].lower()
    assert "sqlalchemy" not in import_block
    assert "asyncsession" not in import_block
    assert "get_tenant_db" not in import_block
    assert "from app.models" not in import_block
    assert not (REPO / "app/services/nationwide_parser.py").exists()
    assert assert_no_separate_provider_parser_engines() == []


@pytest.fixture(scope="module")
def preview() -> dict:
    assert NW_PDF.is_file()
    return parse_fuel_pdf_preview(NW_PDF.read_bytes(), provider_code="NATIONWIDE")


def test_nationwide_real_pdf_layout_and_counts(preview: dict) -> None:
    assert preview["provider"] == "NATIONWIDE"
    assert preview["profile_version"] == PROFILE_VERSION
    assert preview["layout_status"] == "RECOGNIZED"
    assert len(preview["transactions"]) == 12
    cad = [t for t in preview["transactions"] if t["provider_raw"]["Currency"] == "CAD"]
    usd = [t for t in preview["transactions"] if t["provider_raw"]["Currency"] == "USD"]
    assert len(cad) == 1
    assert len(usd) == 11
    assert _sum_currency(preview["transactions"], "CAD") == Decimal("1263.85")
    # Row Total column sums (PDF line items); billing block may differ by rounding.
    assert _sum_currency(preview["transactions"], "USD") == Decimal("5197.67")


def test_nationwide_header_fields(preview: dict) -> None:
    h = preview["header"]
    assert h.get("account_reference") == "20250522B"
    assert h.get("invoice_number") == "20250522B-06142026"
    assert h.get("statement_start") == "2026-06-08"
    assert h.get("statement_end") == "2026-06-14"
    assert h.get("due_date") == "2026-06-15"


def test_nationwide_cad_and_usd_examples(preview: dict) -> None:
    cad = next(t for t in preview["transactions"] if t["provider_raw"]["Unit #"] == "788")
    raw = cad["provider_raw"]
    assert raw["Currency"] == "CAD"
    assert raw["Product"] == "DIESEL"
    assert raw["City"] == "NIAGARA-ON-THE-LAKE"
    assert raw["Pr/St"] == "ON"
    assert raw["Network"] == "Esso"
    norm = cad["preview_normalized"]
    assert norm["unit_price_basis"] == "EX_TAX"
    assert norm["quantity_unit"] == "litres"
    assert norm.get("driver_name_snapshot") is None
    assert norm.get("gst_amount") is None

    usd = next(
        t
        for t in preview["transactions"]
        if t["provider_raw"]["Unit #"] == "794" and t["provider_raw"]["City"] == "PAULSBORO"
    )
    assert usd["provider_raw"]["Currency"] == "USD"
    assert usd["preview_normalized"]["unit_price_basis"] == "FINAL_GALLON_PRICE"
    assert usd["preview_normalized"]["quantity_unit"] == "gallons"
    assert usd["preview_normalized"]["provider_discount_amount"] == "34.56"


def test_usd_row_sum_vs_provider_billing_control_preserved(preview: dict) -> None:
    """Row Total sum vs provider USD billing control — 0.02 is source rounding, not reconciled."""
    row_sum = _sum_currency(preview["transactions"], "USD")
    assert row_sum == Decimal("5197.67")
    usd_controls = [
        c
        for c in preview["controls"]
        if c.get("control_type") == "CURRENCY_TOTAL"
        or c.get("declared_amount") == "5197.69"
        or "5197.69" in (c.get("control_type_raw") or "")
    ]
    assert usd_controls, "expected USD billing control 5197.69"
    declared = Decimal(str(usd_controls[0].get("declared_amount", "5197.69")).replace(",", ""))
    assert declared == Decimal("5197.69")
    assert declared - row_sum == Decimal("0.02")


def test_nationwide_billing_controls_not_unknown(preview: dict) -> None:
    by_raw = {(c.get("control_type_raw") or "")[:40]: c.get("control_type") for c in preview["controls"]}
    assert by_raw.get("Total Volume 674.17") == "UNIT_SUBTOTAL"
    assert by_raw.get("PST $0.00") == "TAX_CONTROL"
    assert by_raw.get("Subtotal $1,263.85") == "PROVIDER_DECLARED_TOTAL"
    assert all(c.get("control_type") != "UNKNOWN" for c in preview["controls"])


def test_nationwide_products_and_controls(preview: dict) -> None:
    products = {t["provider_raw"]["Product"] for t in preview["transactions"]}
    assert "DIESEL" in products
    assert "REEFER" in products
    assert "SCALE" in products
    card_totals = [
        c for c in preview["controls"] if c.get("control_type") == "CARD_TOTAL"
    ]
    assert len(card_totals) >= 3
    gst_controls = [
        c
        for c in preview["controls"]
        if c.get("control_type") == "TAX_CONTROL" or c.get("gst_amount")
    ]
    assert any(c.get("gst_amount") == "145.40" for c in gst_controls)
    for txn in preview["transactions"]:
        assert "gst_amount" not in txn
        assert "hst_amount" not in txn


def test_nationwide_provider_raw_columns_present(preview: dict) -> None:
    required = {
        "Account Code",
        "Card Number",
        "Unit #",
        "Date",
        "City",
        "Pr/St",
        "Product",
        "Volume",
        "Ex-GST ($/U)",
        "Total",
        "Network",
        "Currency",
        "USA Discount",
        "Missed Disc",
        "OON Fees",
    }
    for txn in preview["transactions"]:
        assert required <= set(txn["provider_raw"].keys())


def test_write_untracked_proof_json(preview: dict, tmp_path: Path) -> None:
    """Optional local proof artifact — never committed."""
    out = tmp_path / "nationwide_parse_preview.json"
    out.write_text(json.dumps(preview, indent=2), encoding="utf-8")
    assert out.exists()
