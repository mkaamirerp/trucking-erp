"""Fuel Segment 7: Nationwide as second provider profile on the generic Fuel parser."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.fuel_ai_contract import AI_FORBIDDEN_AUTHORITY_FIELDS, HANDOFF_VERSION, PROFILE
from app.services.fuel_ai_handoff import build_fuel_ai_handoff_payload, route_fuel_source_for_ai
from app.services.fuel_ai_mechanical_validation import validate_fuel_ai_extraction
from app.services.fuel_provider_profile import (
    STRUCTURED_BLOCKED,
    apply_field_aliases,
    assert_no_separate_provider_parser_engines,
    classify_source_row_role,
    list_provider_profile_codes,
    load_provider_profile,
    match_provider_layout,
    structured_export_status,
    suggest_control_type,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
NW_PDF = REPO_ROOT / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"
NW_TEXT = REPO_ROOT / "docs" / "fixtures" / "fuel" / "nationwide_fuel.extracted_text.json"
NW_PROFILE = "NATIONWIDE"
BVD_PROFILE = "BVD"
PROFILE_VERSION = "2026-09-19"


def _pages() -> list[dict]:
    return json.loads(NW_TEXT.read_text(encoding="utf-8"))["pages"]


def _cad_txn_raw() -> dict:
    """Evidenced CAD diesel row from nationwide_fuel.pdf (not invented)."""
    return {
        "Account Code": "20250522B",
        "Card Number": "XXXXX87195",
        "Unit #": "788",
        "Date": "2026-06-09",
        "City": "NIAGARA-ON-THE-LAKE",
        "Pr/St": "ON",
        "Product": "DIESEL",
        "Volume": "674.17",
        "Ex-GST ($/U)": "1.659",
        "Total": "1263.85",
        "Network": "Esso",
        "Currency": "CAD",
        "USA Discount": "0.00",
        "Missed Disc": "0.00",
        "OON Fees": "0.00",
    }


def _usd_txn_raw() -> dict:
    """Evidenced USD diesel row from nationwide_fuel.pdf."""
    return {
        "Account Code": "20250522B",
        "Card Number": "XXXXX07588",
        "Unit #": "794",
        "Date": "2026-06-08",
        "City": "PAULSBORO",
        "Pr/St": "NJ",
        "Product": "DIESEL",
        "Volume": "154.27",
        "Ex-GST ($/U)": "4.685",
        "Total": "722.75",
        "Network": "TA-Petro",
        "Currency": "USD",
        "USA Discount": "34.56",
        "Missed Disc": "0.00",
        "OON Fees": "0.00",
    }


def test_architecture_still_one_parser_two_profiles() -> None:
    assert assert_no_separate_provider_parser_engines() == []
    assert not (REPO_ROOT / "app" / "services" / "nationwide_parser.py").exists()
    master = REPO_ROOT / "app" / "contracts" / "fuel_provider_profiles.json"
    assert master.is_file()
    codes = list_provider_profile_codes()
    assert BVD_PROFILE in codes
    assert NW_PROFILE in codes
    assert not (REPO_ROOT / "app" / "contracts" / "fuel_provider_profiles").is_dir()


def test_nationwide_profile_loads() -> None:
    profile = load_provider_profile(NW_PROFILE)
    assert profile["provider_code"] == "NATIONWIDE"
    assert profile["field_aliases"]["Ex-GST ($/U)"] == "unit_price"
    assert profile["field_semantics"]["unit_price_basis_by_currency"]["CAD"] == "EX_TAX"
    assert profile["field_semantics"]["unit_price_basis_by_currency"]["USD"] == "FINAL_GALLON_PRICE"


def test_nationwide_fixture_layout_recognized() -> None:
    assert NW_PDF.is_file()
    profile = load_provider_profile(NW_PROFILE)
    match = match_provider_layout(profile, page_texts=_pages())
    assert match.status == "RECOGNIZED"
    assert not match.missing_required_anchors


def test_nationwide_layout_mismatch_review() -> None:
    profile = load_provider_profile(NW_PROFILE)
    match = match_provider_layout(profile, document_text="Unrelated invoice without Nationwide anchors")
    assert match.status == "PROVIDER_LAYOUT_UNRECOGNIZED"
    assert match.requires_review is True


def test_cad_row_ex_tax_litres_no_driver_no_row_tax() -> None:
    profile = load_provider_profile(NW_PROFILE)
    h = apply_field_aliases(_cad_txn_raw(), profile=profile)
    assert h["currency_raw"] == "CAD"
    assert h["currency"] == "CAD"
    assert h["unit_price"] == "1.659"
    assert h["unit_price_basis"] == "EX_TAX"
    assert h["quantity"] == "674.17"
    assert h["quantity_unit"] == "litres"
    assert h["total_amount"] == "1263.85"
    assert h["merchant_network"] == "Esso"
    assert h.get("merchant_site") is None  # Network ≠ assumed merchant_site
    assert h.get("driver_name_snapshot") is None
    assert h.get("gst_amount") is None
    assert h.get("hst_amount") is None
    assert "truck_id" not in h
    assert h["provider_raw"]["Network"] == "Esso"


def test_usd_row_final_gallon_gallons_no_inferred_canadian_tax() -> None:
    profile = load_provider_profile(NW_PROFILE)
    h = apply_field_aliases(_usd_txn_raw(), profile=profile)
    assert h["currency_raw"] == "USD"
    assert h["currency"] == "USD"
    assert h["unit_price_basis"] == "FINAL_GALLON_PRICE"
    assert h["quantity_unit"] == "gallons"
    assert h["provider_discount_amount"] == "34.56"
    assert h.get("gst_amount") is None
    assert h.get("qst_amount") is None
    assert h.get("hst_amount") is None
    assert h.get("pst_amount") is None


def test_card_total_and_gst_control_not_purchases() -> None:
    profile = load_provider_profile(NW_PROFILE)
    card_line = "XXXXX87195 Total GST $145.4 QST $0 674.17 $1,263.85 $0.00 $0.00"
    assert classify_source_row_role(profile=profile, line_text=card_line).role == "CONTROL"
    assert suggest_control_type(profile=profile, line_text=card_line) == "CARD_TOTAL"

    gst_line = "GST $145.40"
    assert suggest_control_type(profile=profile, line_text=gst_line) == "TAX_CONTROL"

    # Amount alone is not a purchase.
    amount_only = classify_source_row_role(
        profile=profile, provider_raw={"Total": "1263.85"}
    )
    assert amount_only.role == "UNKNOWN"
    assert amount_only.reason == "INSUFFICIENT_TRANSACTION_EVIDENCE_AMOUNT_ONLY"


def test_cad_and_usd_rows_pass_same_generic_validator() -> None:
    profile = load_provider_profile(NW_PROFILE)
    cad = apply_field_aliases(_cad_txn_raw(), profile=profile)
    usd = apply_field_aliases(_usd_txn_raw(), profile=profile)
    payload = {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": "RECOGNIZED",
        "header": {"invoice_number": "20250522B-06142026"},
        "transactions": [
            {
                "row_role": "TRANSACTION",
                "source_row_order": 1,
                "provider_raw": cad["provider_raw"],
                "transaction_datetime_source": cad["transaction_datetime_source"],
                "transaction_timezone_source": "DATE_ONLY",
                "transaction_date": "2026-06-09",
                "provider_event_type_raw": None,
                "provider_event_type": "PURCHASE",
                "unit_number_snapshot": cad["unit_number_snapshot"],
                "quantity": cad["quantity"],
                "quantity_unit": cad["quantity_unit"],
                "unit_price": cad["unit_price"],
                "unit_price_basis": cad["unit_price_basis"],
                "total_amount": cad["total_amount"],
                "currency_raw": cad["currency_raw"],
                "merchant_network": cad["merchant_network"],
            },
            {
                "row_role": "TRANSACTION",
                "source_row_order": 2,
                "provider_raw": usd["provider_raw"],
                "transaction_datetime_source": usd["transaction_datetime_source"],
                "transaction_timezone_source": "DATE_ONLY",
                "provider_event_type": "PURCHASE",
                "unit_number_snapshot": usd["unit_number_snapshot"],
                "quantity": usd["quantity"],
                "quantity_unit": usd["quantity_unit"],
                "unit_price": usd["unit_price"],
                "unit_price_basis": usd["unit_price_basis"],
                "total_amount": usd["total_amount"],
                "currency_raw": usd["currency_raw"],
                "provider_discount_amount": usd["provider_discount_amount"],
            },
        ],
        "controls": [
            {
                "row_role": "CONTROL",
                "source_row_order": 3,
                "control_type_raw": "XXXXX87195 Total GST $145.4",
                "control_type": "CARD_TOTAL",
                "provider_raw": {"Card Number": "XXXXX87195", "GST": "145.40", "QST": "0"},
                "gst_amount": "145.40",
                "qst_amount": "0.00",
                "declared_amount": "1263.85",
                "currency_raw": "CAD",
            },
            {
                "row_role": "CONTROL",
                "source_row_order": 4,
                "control_type_raw": "GST $145.40",
                "control_type": "TAX_CONTROL",
                "provider_raw": {"GST": "145.40"},
                "gst_amount": "145.40",
                "currency_raw": "CAD",
            },
        ],
        "warnings": [],
    }
    result = validate_fuel_ai_extraction(payload)
    assert result.ok is True
    assert result.payload["transactions"][0]["currency"] == "CAD"
    assert result.payload["transactions"][1]["currency"] == "USD"
    assert result.payload["controls"][0]["control_type"] == "CARD_TOTAL"
    assert result.payload["controls"][1]["control_type"] == "TAX_CONTROL"
    # GST stays on control; CAD txn did not gain inferred tax.
    assert "gst_amount" not in result.payload["transactions"][0]


def test_forbidden_authority_blocked_for_nationwide_too() -> None:
    profile = load_provider_profile(NW_PROFILE)
    poisoned = dict(_cad_txn_raw())
    poisoned["owner_operator_charge_amount"] = "9.99"
    poisoned["truck_id"] = 1
    bad = dict(profile)
    bad["field_aliases"] = {
        **profile["field_aliases"],
        "truck_id": "truck_id",
        "owner_operator_charge_amount": "owner_operator_charge_amount",
    }
    h = apply_field_aliases(poisoned, profile=bad)
    assert "truck_id" not in h
    assert "owner_operator_charge_amount" not in h
    for key in ("financial_responsibility", "settlement_ref", "gate_status"):
        assert key not in h
        assert key in AI_FORBIDDEN_AUTHORITY_FIELDS


def test_handoff_attaches_nationwide_profile_same_pipeline_as_bvd() -> None:
    route = route_fuel_source_for_ai(pdf_source_class="digital_pdf")
    nw = build_fuel_ai_handoff_payload(
        route=route,
        filename="nationwide_fuel.pdf",
        pdf_bytes_ref="docs/fixtures/fuel/nationwide_fuel.pdf",
        expected_provider="NATIONWIDE",
        provider_profile_code=NW_PROFILE,
    )
    bvd = build_fuel_ai_handoff_payload(
        route=route,
        filename="BVD_invoice_972201.pdf",
        pdf_bytes_ref="docs/fixtures/fuel/BVD_invoice_972201.pdf",
        expected_provider="BVD",
        provider_profile_code=BVD_PROFILE,
    )
    assert nw["profile"] == bvd["profile"] == PROFILE
    assert nw["handoff_version"] == bvd["handoff_version"] == HANDOFF_VERSION
    assert nw["document"]["ai_input"] == "original_pdf_bytes"
    assert nw["provider_profile"]["provider_code"] == NW_PROFILE
    assert nw["provider_profile"]["profile_version"] == PROFILE_VERSION
    assert bvd["provider_profile"]["provider_code"] == BVD_PROFILE
    assert bvd["provider_profile"]["profile_version"] == PROFILE_VERSION
    assert PROFILE_VERSION in nw["parser_rule_version"]
    assert "NATIONWIDE" in nw["parser_rule_version"]
    assert NW_PROFILE in nw["parser_rule_version"]
    assert BVD_PROFILE in bvd["parser_rule_version"]


def test_nationwide_csv_companion_blocked_without_sample() -> None:
    profile = load_provider_profile(NW_PROFILE)
    status = structured_export_status(profile)
    assert status["status"] == STRUCTURED_BLOCKED
    assert "CSV" in (status["reason"] or "")
