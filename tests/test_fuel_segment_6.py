"""Fuel Segment 6: BVD as first provider profile on the generic Fuel parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.fuel_ai_contract import AI_FORBIDDEN_AUTHORITY_FIELDS, HANDOFF_VERSION, PROFILE
from app.services.fuel_ai_handoff import (
    ROUTE_DIGITAL_PDF,
    ROUTE_SCANNED_OCR,
    build_fuel_ai_handoff_payload,
    route_fuel_source_for_ai,
)
from app.services.fuel_ai_mechanical_validation import validate_fuel_ai_extraction
from app.services.fuel_provider_profile import (
    STRUCTURED_BLOCKED,
    apply_field_aliases,
    assert_no_separate_provider_parser_engines,
    classify_source_row_role,
    load_provider_profile,
    match_provider_layout,
    structured_export_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BVD_PDF = REPO_ROOT / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"
BVD_TEXT = REPO_ROOT / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.extracted_text.json"
BVD_PROFILE = "BVD"
PROFILE_VERSION = "2026-09-19"


def _bvd_pages() -> list[dict]:
    return json.loads(BVD_TEXT.read_text(encoding="utf-8"))["pages"]


def _txn1_provider_raw() -> dict:
    """Evidenced transaction 1 labels from BVD invoice 972201 (not invented)."""
    return {
        "Auth Code": "A204040667-TA",
        "Driver Name": "JASPREET CHOKAR",
        "Unit #": "1100",
        "Date": "2026-07-23 02:17:56",
        "Site #": "54228",
        "Site Name": "BOWMANVILLE",
        "Site City": "BOWMANVILLE",
        "Prov/ST": "ON",
        "Prod": "TA",
        "QTY": "719.50",
        "Retail": "2.2390",
        "Billed": "2.2390",
        "Pre Tax AMT": "1425.63",
        "HST": "185.33",
        "GST": "0.00",
        "PST": "0.00",
        "QST": "0.00",
        "Disc Rate": "0.0000",
        "Disc AMT": "0.00",
        "Final AMT": "1610.96",
        "CUR": "CN",
        "Card": "4237111",
    }


def test_architecture_one_parser_no_bvd_engine_module() -> None:
    offenders = assert_no_separate_provider_parser_engines()
    assert offenders == []
    # Profiles live in one master JSON under contracts/, not Python parser engines.
    master_path = REPO_ROOT / "app" / "contracts" / "fuel_provider_profiles.json"
    assert master_path.is_file()
    assert not (REPO_ROOT / "app" / "services" / "bvd_parser.py").exists()
    assert not list((REPO_ROOT / "app" / "services").glob("*bvd*parser*.py"))
    assert not (REPO_ROOT / "app" / "contracts" / "fuel_provider_profiles").is_dir()


def test_bvd_profile_loads_and_lists() -> None:
    profile = load_provider_profile(BVD_PROFILE)
    assert profile["provider_code"] == "BVD"
    assert profile["provider_code"] == BVD_PROFILE
    assert profile["profile_version"] == PROFILE_VERSION
    assert "CN" in profile["currency_mappings"]
    assert profile["currency_mappings"]["CN"] == "CAD"
    assert profile["field_aliases"]["Final AMT"] == "total_amount"
    assert profile["field_aliases"]["Billed"] == "unit_price"


def test_bvd_fixture_pdf_and_layout_recognized() -> None:
    assert BVD_PDF.is_file()
    profile = load_provider_profile(BVD_PROFILE)
    pages = _bvd_pages()
    match = match_provider_layout(profile, page_texts=pages)
    assert match.status == "RECOGNIZED"
    assert not match.missing_required_anchors
    assert "Auth Code" in match.matched_anchors


def test_layout_mismatch_is_unrecognized_review() -> None:
    profile = load_provider_profile(BVD_PROFILE)
    match = match_provider_layout(profile, document_text="Random PDF without fuel anchors")
    assert match.status == "PROVIDER_LAYOUT_UNRECOGNIZED"
    assert match.requires_review is True
    assert match.missing_required_anchors


def test_bvd_aliases_hydrate_canonical_preserve_raw_and_cn_cad() -> None:
    profile = load_provider_profile(BVD_PROFILE)
    raw = _txn1_provider_raw()
    hydrated = apply_field_aliases(raw, profile=profile)
    assert hydrated["provider_raw"]["CUR"] == "CN"
    assert hydrated["provider_raw"]["Retail"] == "2.2390"
    assert hydrated["provider_transaction_identity"] == "A204040667-TA"
    assert hydrated["unit_number_snapshot"] == "1100"
    assert hydrated["driver_name_snapshot"] == "JASPREET CHOKAR"
    assert hydrated["card_or_account_id"] == "4237111"
    assert hydrated["quantity"] == "719.50"
    assert hydrated["unit_price"] == "2.2390"
    assert hydrated["unit_price_basis"] == "BILLED"
    assert hydrated["total_amount"] == "1610.96"
    assert hydrated["hst_amount"] == "185.33"
    assert hydrated["currency_raw"] == "CN"
    assert hydrated["currency"] == "CAD"
    assert hydrated["product_code_raw"] == "TA"
    assert hydrated["product_description_raw"] == "Tractor"
    # Retail stays raw evidence; not silently promoted to unit_price overwrite.
    assert hydrated["unit_price"] == raw["Billed"]
    for key in ("truck_id", "driver_id", "owner_operator_charge_amount", "financial_responsibility"):
        assert key not in hydrated


def test_transactions_vs_controls_and_amount_only_unknown() -> None:
    profile = load_provider_profile(BVD_PROFILE)
    assert (
        classify_source_row_role(profile=profile, provider_raw=_txn1_provider_raw()).role
        == "TRANSACTION"
    )
    assert (
        classify_source_row_role(
            profile=profile,
            line_text="SUBTOTAL TA 1,474.00 3,027.44 393.57 0.00 0.00 0.00 0.00 0.00 3,421.01 CN",
        ).role
        == "CONTROL"
    )
    amount_only = classify_source_row_role(
        profile=profile,
        provider_raw={"Final AMT": "3421.01"},
    )
    assert amount_only.role == "UNKNOWN"
    assert amount_only.reason == "INSUFFICIENT_TRANSACTION_EVIDENCE_AMOUNT_ONLY"


def test_bvd_rows_pass_generic_mechanical_validator() -> None:
    profile = load_provider_profile(BVD_PROFILE)
    hydrated = apply_field_aliases(_txn1_provider_raw(), profile=profile)
    payload = {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": "RECOGNIZED",
        "header": {"invoice_number": "972201"},
        "transactions": [
            {
                "row_role": "TRANSACTION",
                "source_row_order": 1,
                "provider_raw": hydrated["provider_raw"],
                "provider_transaction_identity": hydrated["provider_transaction_identity"],
                "transaction_datetime_source": hydrated["transaction_datetime_source"],
                "transaction_timezone_source": "PROVIDER_LOCAL_NO_ZONE",
                "provider_event_type_raw": "PURCHASE",
                "provider_event_type": "PURCHASE",
                "unit_number_snapshot": hydrated["unit_number_snapshot"],
                "quantity": hydrated["quantity"],
                "unit_price": hydrated["unit_price"],
                "hst_amount": hydrated["hst_amount"],
                "pre_tax_amount": hydrated["pre_tax_amount"],
                "total_amount": hydrated["total_amount"],
                "currency_raw": hydrated["currency_raw"],
            }
        ],
        "controls": [
            {
                "row_role": "CONTROL",
                "source_row_order": 2,
                "control_type_raw": "Grand Total",
                "control_type": "INVOICE_TOTAL",
                "provider_raw": {"label": "Grand Total", "FINAL AMOUNT": "3421.01", "CUR": "CN"},
                "declared_amount": "3421.01",
                "currency_raw": "CN",
            }
        ],
        "warnings": [],
    }
    result = validate_fuel_ai_extraction(payload)
    assert result.ok is True
    assert result.payload["transactions"][0]["currency"] == "CAD"
    assert result.payload["controls"][0]["row_role"] == "CONTROL"
    assert result.payload["transactions"][0]["currency_raw"] == "CN"


def test_forbidden_authority_cannot_enter_via_profile_aliases() -> None:
    profile = load_provider_profile(BVD_PROFILE)
    poisoned = dict(_txn1_provider_raw())
    poisoned["truck_id"] = 99
    poisoned["owner_operator_charge_amount"] = "1.00"
    # Even if aliases were wrongly extended, apply_field_aliases strips forbidden.
    bad_profile = dict(profile)
    bad_profile["field_aliases"] = {
        **profile["field_aliases"],
        "truck_id": "truck_id",
        "owner_operator_charge_amount": "owner_operator_charge_amount",
    }
    hydrated = apply_field_aliases(poisoned, profile=bad_profile)
    assert "truck_id" not in hydrated
    assert "owner_operator_charge_amount" not in hydrated
    for key in AI_FORBIDDEN_AUTHORITY_FIELDS:
        assert key not in hydrated


def test_credit_sign_preserved_through_generic_validator() -> None:
    result = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "RECOGNIZED",
            "header": {},
            "transactions": [
                {
                    "row_role": "TRANSACTION",
                    "source_row_order": 1,
                    "provider_raw": {"Auth Code": "CRED-1", "Final AMT": "-10.00", "CUR": "CN"},
                    "transaction_datetime_source": "2026-07-23 02:17:56",
                    "transaction_timezone_source": "PROVIDER_LOCAL_NO_ZONE",
                    "provider_event_type_raw": "CREDIT",
                    "provider_event_type": "CREDIT",
                    "total_amount": "-10.00",
                    "currency_raw": "CN",
                }
            ],
            "controls": [],
            "warnings": [],
        }
    )
    assert result.ok is True
    assert result.payload["transactions"][0]["provider_event_type"] == "CREDIT"
    assert result.payload["transactions"][0]["total_amount"] == "-10.00"


def test_handoff_attaches_bvd_profile_digital_and_scanned() -> None:
    digital = route_fuel_source_for_ai(pdf_source_class="digital_pdf")
    assert digital.route == ROUTE_DIGITAL_PDF
    payload = build_fuel_ai_handoff_payload(
        route=digital,
        filename="BVD_invoice_972201.pdf",
        pdf_bytes_ref="docs/fixtures/fuel/BVD_invoice_972201.pdf",
        expected_provider="BVD",
        provider_profile_code=BVD_PROFILE,
    )
    assert payload["provider_profile"]["provider_code"] == BVD_PROFILE
    assert payload["provider_profile"]["profile_version"] == PROFILE_VERSION
    assert payload["document"]["ai_input"] == "original_pdf_bytes"
    assert payload["document"]["pages"] is None
    assert "BVD" in payload["parser_rule_version"]
    assert PROFILE_VERSION in payload["parser_rule_version"]

    scanned = route_fuel_source_for_ai(pdf_source_class="scanned_image_pdf")
    assert scanned.route == ROUTE_SCANNED_OCR
    scanned_payload = build_fuel_ai_handoff_payload(
        route=scanned,
        filename="scan.pdf",
        ocr_pages=_bvd_pages(),
        provider_profile_code=BVD_PROFILE,
    )
    assert scanned_payload["document"]["ai_input"] == "ocr_text"
    assert scanned_payload["provider_profile"]["provider_code"] == "BVD"


def test_structured_bvd_export_blocked_without_sample() -> None:
    profile = load_provider_profile(BVD_PROFILE)
    status = structured_export_status(profile)
    assert status["status"] == STRUCTURED_BLOCKED
    assert "T-Chek" in (status["reason"] or "") or "evidence" in (status["reason"] or "").lower()


def test_unrecognized_layout_mechanical_review() -> None:
    result = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "PROVIDER_LAYOUT_UNRECOGNIZED",
            "header": {},
            "transactions": [],
            "controls": [],
            "warnings": [],
        }
    )
    assert result.requires_review is True
