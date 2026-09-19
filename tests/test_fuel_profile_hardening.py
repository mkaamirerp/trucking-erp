"""Generic Fuel provider-profile hardening (architecture correction before Segment 8)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.fuel_ai_contract import HANDOFF_VERSION, PROFILE
from app.services.fuel_ai_handoff import build_fuel_ai_handoff_payload, route_fuel_source_for_ai
from app.services.fuel_ai_mechanical_validation import validate_fuel_ai_extraction
from app.services.fuel_provider_profile import (
    LAYOUT_AMBIGUOUS,
    LAYOUT_UNRECOGNIZED,
    REASON_AMOUNT_ONLY,
    apply_field_aliases,
    assert_no_separate_provider_parser_engines,
    audit_generic_provider_source_literals,
    classify_source_row_role,
    get_provider_profile_for_code,
    list_provider_profile_codes,
    load_provider_profile,
    match_provider_layout,
    normalize_layout_text,
    resolve_provider_profile_for_document,
)

REPO = Path(__file__).resolve().parents[1]
BVD = "BVD"
NW = "NATIONWIDE"
PROFILE_VERSION = "2026-09-19"


def test_architecture_guard_is_executed_and_clean() -> None:
    offenders = assert_no_separate_provider_parser_engines()
    assert offenders == []
    assert audit_generic_provider_source_literals() == []


def test_control_word_inside_transaction_value_is_not_control() -> None:
    profile = load_provider_profile(BVD)
    # "TOTAL" / "Grand Total" appear only inside merchant/site values — not row labels.
    raw = {
        "Auth Code": "A204040667-TA",
        "Site Name": "GRAND TOTAL FUEL STOP",
        "Driver Name": "TOTAL SMITH",
        "Final AMT": "10.00",
        "CUR": "CN",
    }
    result = classify_source_row_role(profile=profile, provider_raw=raw)
    assert result.role == "TRANSACTION"
    assert result.reason == "TRANSACTION_FIELD_MARKERS_PRESENT"


def test_deterministic_field_equals_control_rule() -> None:
    profile = load_provider_profile(NW)
    result = classify_source_row_role(
        profile=profile,
        provider_raw={"row_label": "CARD_TOTAL", "Total": "1263.85"},
    )
    assert result.role == "CONTROL"
    assert result.reason == "CONTROL_RULE_MATCHED"


def test_amount_only_has_explicit_reason() -> None:
    profile = load_provider_profile(BVD)
    result = classify_source_row_role(profile=profile, provider_raw={"Final AMT": "99.00"})
    assert result.role == "UNKNOWN"
    assert result.reason == REASON_AMOUNT_ONLY
    assert result.requires_review is True


def test_bvd_cur_and_billed_are_profile_aliases_only() -> None:
    profile = load_provider_profile(BVD)
    h = apply_field_aliases(
        {"CUR": "CN", "Billed": "2.2390", "Auth Code": "A1", "Final AMT": "1.00"},
        profile=profile,
    )
    assert h["currency_raw"] == "CN"
    assert h["currency"] == "CAD"
    assert h["unit_price"] == "2.2390"
    assert h["unit_price_basis"] == "BILLED"
    # Generic module must not hardcode CUR/Billed.
    assert audit_generic_provider_source_literals() == []


def test_nationwide_currency_label_via_same_engine() -> None:
    profile = load_provider_profile(NW)
    h = apply_field_aliases(
        {
            "Card Number": "XXXXX07588",
            "Volume": "154.27",
            "Ex-GST ($/U)": "4.685",
            "Currency": "USD",
            "Total": "722.75",
        },
        profile=profile,
    )
    assert h["currency_raw"] == "USD"
    assert h["currency"] == "USD"
    assert h["unit_price_basis"] == "FINAL_GALLON_PRICE"


def test_synthetic_provider_currency_alias_via_same_engine() -> None:
    """Second provider with a differently named currency field — same generic apply path."""
    synthetic = {
        "provider_code": "SYNTH",
        "profile_version": "test",
        "field_aliases": {"Ccy Code": "currency_raw", "Net": "total_amount"},
        "currency_mappings": {"CN": "CAD"},
        "field_semantics": {},
    }
    h = apply_field_aliases({"Ccy Code": "CN", "Net": "10.00"}, profile=synthetic)
    assert h["currency_raw"] == "CN"
    assert h["currency"] == "CAD"
    assert h["total_amount"] == "10.00"
    assert "Ccy Code" not in h or h.get("currency_raw") == "CN"


def test_layout_resolver_zero_one_many() -> None:
    bvd_pages = json.loads(
        (REPO / "docs/fixtures/fuel/BVD_invoice_972201.extracted_text.json").read_text()
    )["pages"]
    one = resolve_provider_profile_for_document("BVD", page_texts=bvd_pages)
    assert one.status == "RECOGNIZED"
    assert one.profile is not None
    assert one.profile["provider_code"] == BVD
    assert one.profile["profile_version"] == PROFILE_VERSION

    zero = resolve_provider_profile_for_document("BVD", document_text="unrelated document")
    assert zero.status == LAYOUT_UNRECOGNIZED
    assert zero.profile is None
    assert zero.requires_review is True

    # Simulate two BVD profiles both matching the same anchors → ambiguous.
    primary = load_provider_profile(BVD)
    twin = dict(primary)
    twin["profile_version"] = "twin-test"
    # Temporary in-memory resolution path: call match on both manually.
    m1 = match_provider_layout(primary, page_texts=bvd_pages)
    m2 = match_provider_layout(twin, page_texts=bvd_pages)
    assert m1.status == "RECOGNIZED" and m2.status == "RECOGNIZED"
    # Document the contract of the resolver when multiple files exist:
    # (integration covered when a second on-disk profile is present)
    assert LAYOUT_AMBIGUOUS == "PROVIDER_LAYOUT_AMBIGUOUS"


def test_layout_resolver_ambiguous_with_temp_second_profile(monkeypatch) -> None:
    """Multi-layout ambiguity remains a REVIEW outcome (future layouts / tests)."""
    import copy

    import app.services.fuel_provider_profile as mod

    primary = load_provider_profile(BVD)
    twin_version = "twin-layout-test"
    twin = dict(primary)
    twin["profile_version"] = twin_version

    def _two_bvd(_provider_code: str):
        return [copy.deepcopy(primary), copy.deepcopy(twin)]

    monkeypatch.setattr(mod, "list_provider_profiles_for_provider", _two_bvd)
    bvd_pages = json.loads(
        (REPO / "docs/fixtures/fuel/BVD_invoice_972201.extracted_text.json").read_text()
    )["pages"]
    result = mod.resolve_provider_profile_for_document("BVD", page_texts=bvd_pages)
    assert result.status == LAYOUT_AMBIGUOUS
    assert result.profile is None
    assert set(result.matched_profile_versions) == {PROFILE_VERSION, twin_version}


def test_anchor_normalization_case_and_whitespace() -> None:
    profile = load_provider_profile(BVD)
    assert normalize_layout_text("Fuel   Card\nTransactions") == "fuel card transactions"
    messy = "fuel card transactions\nauth code\ndriver name\nunit #\nfinal amt\ncur"
    match = match_provider_layout(profile, document_text=messy)
    assert match.status == "RECOGNIZED"


def test_nationwide_uom_fallback_scoped_and_overridable() -> None:
    nw = load_provider_profile(NW)
    bvd = load_provider_profile(BVD)
    assert "quantity_unit_by_currency_fallback" in nw["field_semantics"]
    assert "quantity_unit_by_currency_fallback" not in bvd.get("field_semantics", {})
    # Evidence pointers present on Nationwide profile only.
    assert nw["evidence"]["uom_fallback_evidence"]
    assert nw["evidence"]["price_basis_evidence"]

    cad = apply_field_aliases(
        {
            "Card Number": "XXXXX87195",
            "Volume": "674.17",
            "Ex-GST ($/U)": "1.659",
            "Currency": "CAD",
            "Total": "1263.85",
        },
        profile=nw,
    )
    assert cad["quantity_unit"] == "litres"
    assert cad["unit_price_basis"] == "EX_TAX"

    explicit = apply_field_aliases(
        {
            "Card Number": "XXXXX87195",
            "Volume": "674.17",
            "Ex-GST ($/U)": "1.659",
            "Currency": "CAD",
            "Total": "1263.85",
        },
        profile=nw,
        existing={"quantity_unit": "imperial_gallons"},
    )
    assert explicit["quantity_unit"] == "imperial_gallons"

    # BVD CAD (via CN) must NOT invent litres — no global CAD→L rule.
    bvd_row = apply_field_aliases(
        {"Auth Code": "A1", "CUR": "CN", "Billed": "2.00", "QTY": "10", "Final AMT": "20"},
        profile=bvd,
    )
    assert bvd_row.get("quantity_unit") is None
    assert bvd_row["currency"] == "CAD"


def test_cross_provider_same_pipeline() -> None:
    from app.services.fuel_provider_profile import (
        list_master_provider_codes,
        load_master_provider_profiles,
    )

    assert list_master_provider_codes() == ["BVD", "NATIONWIDE"]
    master = load_master_provider_profiles()
    assert set(master.keys()) == {"BVD", "NATIONWIDE"}
    assert list_provider_profile_codes() == ["BVD", "NATIONWIDE"]
    assert get_provider_profile_for_code("BVD")["provider_code"] == BVD
    assert get_provider_profile_for_code("BVD")["profile_version"] == PROFILE_VERSION
    assert get_provider_profile_for_code("NATIONWIDE")["provider_code"] == NW
    assert get_provider_profile_for_code("NATIONWIDE")["profile_version"] == PROFILE_VERSION
    assert load_provider_profile("BVD")["profile_version"] == PROFILE_VERSION
    assert load_provider_profile("NATIONWIDE")["profile_version"] == PROFILE_VERSION
    # Legacy statement_v1 identities are gone.
    import pytest
    with pytest.raises(FileNotFoundError):
        load_provider_profile("bvd_statement_v1")
    with pytest.raises(FileNotFoundError):
        load_provider_profile("nationwide_statement_v1")

    route = route_fuel_source_for_ai(pdf_source_class="digital_pdf")
    bvd_h = build_fuel_ai_handoff_payload(
        route=route,
        filename="bvd.pdf",
        pdf_bytes_ref="docs/fixtures/fuel/BVD_invoice_972201.pdf",
        provider_profile_code=BVD,
    )
    nw_h = build_fuel_ai_handoff_payload(
        route=route,
        filename="nw.pdf",
        pdf_bytes_ref="docs/fixtures/fuel/nationwide_fuel.pdf",
        provider_profile_code=NW,
    )
    assert bvd_h["profile"] == nw_h["profile"] == PROFILE
    assert bvd_h["handoff_version"] == nw_h["handoff_version"] == HANDOFF_VERSION
    assert bvd_h["document"]["ai_input"] == nw_h["document"]["ai_input"] == "original_pdf_bytes"

    bvd_prof = load_provider_profile(BVD)
    nw_prof = load_provider_profile(NW)
    bvd_row = apply_field_aliases(
        {
            "Auth Code": "A204040667-TA",
            "CUR": "CN",
            "Billed": "2.2390",
            "Final AMT": "1610.96",
            "QTY": "719.50",
        },
        profile=bvd_prof,
    )
    nw_row = apply_field_aliases(
        {
            "Card Number": "XXXXX87195",
            "Volume": "674.17",
            "Ex-GST ($/U)": "1.659",
            "Currency": "CAD",
            "Total": "1263.85",
        },
        profile=nw_prof,
    )
    payload = {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": "RECOGNIZED",
        "header": {},
        "transactions": [
            {
                "row_role": "TRANSACTION",
                "source_row_order": 1,
                "provider_raw": bvd_row["provider_raw"],
                "transaction_datetime_source": "2026-07-23 02:17:56",
                "transaction_timezone_source": "PROVIDER_LOCAL_NO_ZONE",
                "provider_event_type": "PURCHASE",
                "total_amount": bvd_row["total_amount"],
                "currency_raw": bvd_row["currency_raw"],
                "quantity": bvd_row["quantity"],
                "unit_price": bvd_row["unit_price"],
            },
            {
                "row_role": "TRANSACTION",
                "source_row_order": 2,
                "provider_raw": nw_row["provider_raw"],
                "transaction_datetime_source": "2026-06-09",
                "transaction_timezone_source": "DATE_ONLY",
                "provider_event_type": "PURCHASE",
                "total_amount": nw_row["total_amount"],
                "currency_raw": nw_row["currency_raw"],
                "quantity": nw_row["quantity"],
                "unit_price": nw_row["unit_price"],
            },
        ],
        "controls": [
            {
                "row_role": "CONTROL",
                "source_row_order": 3,
                "control_type": "CARD_TOTAL",
                "provider_raw": {"row_label": "CARD_TOTAL"},
                "declared_amount": "1263.85",
                "currency_raw": "CAD",
            }
        ],
        "warnings": [],
    }
    result = validate_fuel_ai_extraction(payload)
    assert result.ok is True
    assert result.payload["transactions"][0]["currency"] == "CAD"
    assert result.payload["transactions"][1]["currency"] == "CAD"
    assert result.payload["controls"][0]["control_type"] == "CARD_TOTAL"
    assert assert_no_separate_provider_parser_engines() == []
