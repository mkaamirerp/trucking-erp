"""Fuel Segment 5: AI handoff contract + mechanical validator."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.fuel_ai_contract import (
    AI_FORBIDDEN_AUTHORITY_FIELDS,
    HANDOFF_VERSION,
    PROFILE,
    load_fuel_ai_handoff_contract,
    parser_rule_version_for_persistence,
)
from app.services.fuel_ai_handoff import (
    ROUTE_DIGITAL_PDF,
    ROUTE_SCANNED_OCR,
    ROUTE_STRUCTURED_BYPASS,
    build_fuel_ai_handoff_payload,
    persist_parser_rule_version_on_batch,
    route_fuel_source_for_ai,
)
from app.services.fuel_ai_mechanical_validation import (
    assert_no_forbidden_authority_fields,
    validate_fuel_ai_extraction,
)


def test_contract_loads_with_required_envelope() -> None:
    doc = load_fuel_ai_handoff_contract()
    assert doc["handoff_version"] == HANDOFF_VERSION
    assert doc["profile"] == PROFILE
    assert "global_rules" in doc
    assert "output_schema" in doc
    assert "transactions" in doc["output_schema"]["properties"]
    assert "controls" in doc["output_schema"]["properties"]
    forbidden = set(doc["ai_forbidden_authority_fields"])
    for key in (
        "truck_id",
        "driver_id",
        "owner_operator_payee_id",
        "owner_operator_charge_amount",
        "financial_responsibility",
        "oo_pricing_mode",
        "settlement_ref",
        "gate_status",
    ):
        assert key in forbidden
        assert key in AI_FORBIDDEN_AUTHORITY_FIELDS


def test_routing_digital_scanned_structured() -> None:
    digital = route_fuel_source_for_ai(pdf_source_class="digital_pdf")
    assert digital.route == ROUTE_DIGITAL_PDF
    assert digital.bypass_ai is False
    assert digital.ai_input_mode == "original_pdf_bytes_plus_contract"

    scanned = route_fuel_source_for_ai(pdf_source_class="scanned_image")
    assert scanned.route == ROUTE_SCANNED_OCR
    assert scanned.ai_input_mode == "ocr_text_plus_contract"

    structured = route_fuel_source_for_ai(source_type="STRUCTURED_FILE")
    assert structured.route == ROUTE_STRUCTURED_BYPASS
    assert structured.bypass_ai is True


def test_digital_handoff_rejects_embedded_text_substitution() -> None:
    route = route_fuel_source_for_ai(pdf_source_class="digital_pdf")
    with pytest.raises(ValueError, match="original PDF bytes"):
        build_fuel_ai_handoff_payload(
            route=route,
            filename="stmt.pdf",
            pdf_bytes_ref="s3://bucket/stmt.pdf",
            digital_embedded_text="Card 123 Total 10.00",
        )
    payload = build_fuel_ai_handoff_payload(
        route=route,
        filename="stmt.pdf",
        pdf_bytes_ref="s3://bucket/stmt.pdf",
        expected_provider="BVD",
    )
    assert payload["bypass_ai"] is False
    assert payload["document"]["ai_input"] == "original_pdf_bytes"
    assert payload["document"]["pages"] is None
    assert payload["document"]["full_text"] is None
    assert payload["acquisition"]["embedded_text_substituted"] is False
    assert payload["contract"]["provider_context"]["expected_provider"] == "BVD"


def test_scanned_handoff_uses_ocr_pages() -> None:
    route = route_fuel_source_for_ai(pdf_source_class="scanned_image_pdf")
    payload = build_fuel_ai_handoff_payload(
        route=route,
        filename="scan.pdf",
        ocr_pages=[{"page_number": 1, "text": "OCR LINE"}],
    )
    assert payload["document"]["ai_input"] == "ocr_text"
    assert payload["document"]["pages"][0]["text"] == "OCR LINE"


def test_structured_bypass_and_parser_version_persistence() -> None:
    route = route_fuel_source_for_ai(source_type="STRUCTURED_FILE")
    payload = build_fuel_ai_handoff_payload(route=route, filename="export.dat")
    assert payload["bypass_ai"] is True
    assert payload["document"] is None
    batch = SimpleNamespace(parser_rule_version=None)
    ver = persist_parser_rule_version_on_batch(batch, handoff=payload)
    assert ver == parser_rule_version_for_persistence()
    assert batch.parser_rule_version == ver


def _minimal_txn(**overrides):
    row = {
        "row_role": "TRANSACTION",
        "source_row_order": 1,
        "provider_raw": {"line": "1"},
        "transaction_datetime_source": "2026-07-23 02:17:56",
        "transaction_timezone_source": "PROVIDER_LOCAL_NO_ZONE",
        "provider_event_type_raw": "PURCHASE",
        "provider_event_type": "PURCHASE",
        "currency_raw": "CN",
        "total_amount": "-12.3400",
    }
    row.update(overrides)
    return row


def test_mechanical_validation_accepts_valid_txn_and_control() -> None:
    payload = {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": "RECOGNIZED",
        "header": {"invoice_number": "972201"},
        "transactions": [
            _minimal_txn(
                total_amount="12.3400",
                currency_raw="CN",
            )
        ],
        "controls": [
            {
                "row_role": "CONTROL",
                "source_row_order": 2,
                "control_type_raw": "CARD TOTAL",
                "control_type": "CARD_TOTAL",
                "provider_raw": {},
                "declared_amount": "12.3400",
                "currency_raw": "CAD",
            }
        ],
        "warnings": [],
    }
    result = validate_fuel_ai_extraction(payload)
    assert result.ok is True
    assert result.payload["transactions"][0]["currency"] == "CAD"
    assert result.payload["controls"][0]["row_role"] == "CONTROL"


def test_mechanical_rejects_float_and_forbidden_authority_fields() -> None:
    payload = {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": "RECOGNIZED",
        "header": {},
        "transactions": [
            _minimal_txn(
                total_amount=12.34,  # float forbidden
                truck_id=99,
                owner_operator_charge_amount="1.00",
            )
        ],
        "controls": [],
        "warnings": [],
    }
    result = validate_fuel_ai_extraction(payload)
    assert result.ok is False
    assert any("float" in e for e in result.errors)
    assert any("truck_id" in e for e in result.errors)
    assert "truck_id" not in result.payload["transactions"][0]
    assert "owner_operator_charge_amount" not in result.payload["transactions"][0]


def test_mechanical_source_row_exclusivity_and_role_separation() -> None:
    payload = {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": "RECOGNIZED",
        "header": {},
        "transactions": [_minimal_txn(source_row_order=1, total_amount="1.0000")],
        "controls": [
            {
                "row_role": "CONTROL",
                "source_row_order": 1,
                "control_type_raw": "GST",
                "control_type": "TAX_CONTROL",
                "provider_raw": {},
            }
        ],
        "warnings": [],
    }
    result = validate_fuel_ai_extraction(payload)
    assert result.ok is False
    assert any("exclusivity" in e for e in result.errors)


def test_unknown_event_not_forced_to_purchase_and_credit_sign_warning() -> None:
    unknown = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "RECOGNIZED",
            "header": {},
            "transactions": [
                _minimal_txn(
                    provider_event_type_raw="WEIRD_TOKEN",
                    provider_event_type="PURCHASE",
                    total_amount="5.0000",
                )
            ],
            "controls": [],
            "warnings": [],
        }
    )
    assert unknown.ok is False or unknown.requires_review
    assert unknown.payload["transactions"][0]["provider_event_type"] == "UNKNOWN"

    credit = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "RECOGNIZED",
            "header": {},
            "transactions": [
                _minimal_txn(
                    provider_event_type_raw="CREDIT",
                    provider_event_type="CREDIT",
                    total_amount="5.0000",
                )
            ],
            "controls": [],
            "warnings": [],
        }
    )
    assert any("sign" in w.lower() or "CREDIT" in w for w in credit.warnings)


def test_unrecognized_layout_requires_review() -> None:
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
    assert "PROVIDER_LAYOUT_UNRECOGNIZED" in result.review_reasons


def test_assert_no_forbidden_authority_fields() -> None:
    assert_no_forbidden_authority_fields({"total_amount": "1.0", "unit_number_snapshot": "1100"})
    with pytest.raises(ValueError):
        assert_no_forbidden_authority_fields({"truck_id": 1})


def test_control_with_amount_cannot_masquerade_as_transaction() -> None:
    """Amount alone does not authorize treating a control as a purchase."""
    leaked = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "RECOGNIZED",
            "header": {},
            "transactions": [
                _minimal_txn(
                    source_row_order=1,
                    total_amount="145.4000",
                    control_type_raw="GST",
                    control_type="TAX_CONTROL",
                    provider_event_type="PURCHASE",
                )
            ],
            "controls": [],
            "warnings": [],
        }
    )
    assert leaked.ok is False
    assert any("control markers" in e for e in leaked.errors)

    # Same amount as a proper CONTROL stays a control, not a purchase.
    ok_control = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "RECOGNIZED",
            "header": {},
            "transactions": [],
            "controls": [
                {
                    "row_role": "CONTROL",
                    "source_row_order": 1,
                    "control_type_raw": "GST",
                    "control_type": "TAX_CONTROL",
                    "declared_amount": "145.4000",
                    "provider_raw": {"label": "GST"},
                    "currency_raw": "CAD",
                }
            ],
            "warnings": [],
        }
    )
    assert ok_control.ok is True
    assert ok_control.payload["controls"][0]["row_role"] == "CONTROL"
    assert ok_control.payload["transactions"] == []


def test_provider_identities_remain_separate_from_truckerp_id() -> None:
    """provider_transaction_identity / source_row_id are not TruckERP canonical id."""
    result = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "RECOGNIZED",
            "header": {},
            "transactions": [
                _minimal_txn(
                    source_row_order=7,
                    source_row_id="pdf-row-7",
                    provider_transaction_identity="A204040667-TA",
                    total_amount="10.0000",
                )
            ],
            "controls": [],
            "warnings": [],
        }
    )
    assert result.ok is True
    txn = result.payload["transactions"][0]
    assert txn["provider_transaction_identity"] == "A204040667-TA"
    assert txn["source_row_id"] == "pdf-row-7"
    assert txn["source_row_order"] == 7
    assert "id" not in txn
    assert "truck_id" not in txn
    # Omitted provider identity is allowed (null/absent); never invented.
    omitted = validate_fuel_ai_extraction(
        {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "layout_status": "RECOGNIZED",
            "header": {},
            "transactions": [_minimal_txn(source_row_order=8, total_amount="1.0000")],
            "controls": [],
            "warnings": [],
        }
    )
    assert omitted.ok is True
    assert omitted.payload["transactions"][0].get("provider_transaction_identity") is None
