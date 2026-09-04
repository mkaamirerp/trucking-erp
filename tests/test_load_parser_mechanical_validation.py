"""Mechanical post-model validation — unit tests (no OpenAI, no diagnostics)."""

from __future__ import annotations

import copy
import importlib
import math
from typing import Any

import pytest

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_parser_mechanical_validation import apply_load_parser_mechanical_validation


def _base_response(**overrides: Any) -> LoadDocumentParseResponse:
    payload: dict[str, Any] = {
        "document": {"filename": "x.pdf"},
        "extracted": {
            "broker_name_snapshot": "Armstrong Transport Group",
            "broker_contact_name_snapshot": "Loflin Phillips",
            "broker_contact_phone_snapshot": "208-751-8073",
            "broker_contact_email_snapshot": "l.phillips@armstrongtransport.com",
            "broker_load_reference": "3872125-1",
            "broker_mc_number_snapshot": "555609",
            "broker_dot_number_snapshot": None,
            "rate": 1800.0,
            "customer_rate": None,
            "miles": 750.0,
            "estimated_weight": 43000,
            "references": [{"kind": "po_number", "value": "PO-99"}],
            "stops": [
                {
                    "stop_type": "pickup",
                    "sequence": 0,
                    "facility_name": "NCG",
                    "city": "Chicago",
                    "state_or_province": "IL",
                    "appointment_date": "2025-10-28",
                    "appointment_time_text": "06:30-10:00",
                },
                {
                    "stop_type": "delivery",
                    "sequence": 1,
                    "facility_name": "ICS",
                    "city": "Reidsville",
                    "state_or_province": "NC",
                    "appointment_date": "2025-10-29",
                    "appointment_time_text": "07:00-12:00",
                },
            ],
        },
        "raw_text": (
            "Armstrong Transport Group Load #3872125-1 Rate: $1,800.00 "
            "Loflin Phillips 208-751-8073 l.phillips@armstrongtransport.com MC 555609"
        ),
        "warnings": [],
        "field_confidence": {},
        "context": {"parse_path": "test"},
    }
    for k, v in overrides.items():
        if k == "extracted" and isinstance(v, dict):
            payload["extracted"] = {**payload["extracted"], **v}
        else:
            payload[k] = v
    return LoadDocumentParseResponse.model_validate(payload)


def _exclusion(**overrides: Any) -> dict[str, Any]:
    base = {
        "names": ["IK Logistics", "9582479 Canada Inc"],
        "mc_numbers": ["1397898"],
        "usdot_numbers": ["3842541"],
        "phones": ["6472419696"],
        "emails": ["fleet@iklogistics.com"],
        "email_domains": ["iklogistics.com"],
        "addresses": [],
    }
    base.update(overrides)
    return base


# --- Tenant exclusion ---


def test_tenant_name_match_nulls_broker_name() -> None:
    res = _base_response(extracted={"broker_name_snapshot": "IK Logistics"})
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_name_snapshot is None
    assert "tenant_identity_match: broker_name_snapshot" in out.warnings


def test_tenant_name_match_is_case_and_space_normalized() -> None:
    res = _base_response(extracted={"broker_name_snapshot": "  ik   logistics "})
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_name_snapshot is None


def test_unrelated_broker_name_preserved() -> None:
    res = _base_response()
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_name_snapshot == "Armstrong Transport Group"


def test_no_fuzzy_company_match() -> None:
    """Substring / similar names must not match — exact normalized key only."""
    res = _base_response(extracted={"broker_name_snapshot": "IK Logistics Solutions LLC"})
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_name_snapshot == "IK Logistics Solutions LLC"


def test_tenant_email_match_nulls() -> None:
    res = _base_response(extracted={"broker_contact_email_snapshot": "FLEET@IKLOGISTICS.COM"})
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_contact_email_snapshot is None
    assert "tenant_identity_match: broker_contact_email_snapshot" in out.warnings


def test_tenant_phone_match_nulls() -> None:
    res = _base_response(extracted={"broker_contact_phone_snapshot": "+1 (647) 241-9696"})
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_contact_phone_snapshot is None
    assert "tenant_identity_match: broker_contact_phone_snapshot" in out.warnings


def test_tenant_mc_match_nulls() -> None:
    res = _base_response(extracted={"broker_mc_number_snapshot": "MC-1397898"})
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_mc_number_snapshot is None
    assert "tenant_identity_match: broker_mc_number_snapshot" in out.warnings


def test_tenant_dot_match_nulls() -> None:
    res = _base_response(extracted={"broker_dot_number_snapshot": "USDOT 3842541"})
    out = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert out.extracted.broker_dot_number_snapshot is None
    assert "tenant_identity_match: broker_dot_number_snapshot" in out.warnings


# --- Contacts ---


def test_email_in_contact_name_rejected() -> None:
    res = _base_response(extracted={"broker_contact_name_snapshot": "agent@broker.com"})
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_contact_name_snapshot is None
    assert any("invalid_contact_name" in w for w in out.warnings)


def test_phone_like_contact_name_rejected() -> None:
    res = _base_response(extracted={"broker_contact_name_snapshot": "208-751-8073"})
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_contact_name_snapshot is None


def test_malformed_email_rejected() -> None:
    res = _base_response(extracted={"broker_contact_email_snapshot": "not-an-email"})
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_contact_email_snapshot is None
    assert "invalid_email: broker_contact_email_snapshot" in out.warnings


def test_valid_contact_preserved() -> None:
    res = _base_response()
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_contact_name_snapshot == "Loflin Phillips"
    assert out.extracted.broker_contact_email_snapshot == "l.phillips@armstrongtransport.com"
    assert out.extracted.broker_contact_phone_snapshot == "208-751-8073"


def test_named_contact_generic_carriers_mailbox_nulled() -> None:
    res = _base_response(
        extracted={
            "broker_contact_name_snapshot": "Jane Agent",
            "broker_contact_email_snapshot": "carriers@example.com",
            "broker_contact_phone_snapshot": "208-751-8073",
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_contact_email_snapshot is None
    assert "generic_company_mailbox: broker_contact_email_snapshot" in out.warnings
    assert out.extracted.broker_contact_phone_snapshot == "208-751-8073"
    assert out.extracted.broker_contact_name_snapshot == "Jane Agent"


def test_named_contact_generic_dispatch_mailbox_nulled() -> None:
    res = _base_response(
        extracted={
            "broker_contact_name_snapshot": "Jane Agent",
            "broker_contact_email_snapshot": "dispatch@example.com",
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_contact_email_snapshot is None
    assert "generic_company_mailbox: broker_contact_email_snapshot" in out.warnings


def test_named_contact_person_email_preserved() -> None:
    res = _base_response(
        extracted={
            "broker_contact_name_snapshot": "Jane Agent",
            "broker_contact_email_snapshot": "person.name@example.com",
            "broker_contact_phone_snapshot": "208-751-8073",
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_contact_email_snapshot == "person.name@example.com"
    assert out.extracted.broker_contact_phone_snapshot == "208-751-8073"
    assert not any("generic_company_mailbox" in w for w in out.warnings)


# --- Numeric ---


def test_valid_positive_rate_preserved() -> None:
    out = apply_load_parser_mechanical_validation(_base_response())
    assert out.extracted.rate == 1800.0


def test_zero_and_negative_rate_rejected() -> None:
    out0 = apply_load_parser_mechanical_validation(_base_response(extracted={"rate": 0}))
    assert out0.extracted.rate is None
    out_neg = apply_load_parser_mechanical_validation(_base_response(extracted={"rate": -5}))
    assert out_neg.extracted.rate is None


def test_nan_inf_rate_rejected() -> None:
    # Bypass pydantic construction by dumping and re-validating after patch is hard;
    # use model_construct for non-finite then run validator.
    res = _base_response()
    payload = res.model_dump(mode="json")
    payload["extracted"]["rate"] = float("nan")
    # model_validate may reject NaN — construct manually then call validator internals via dump path
    from app.schemas.load_document_parse import LoadParseExtractedFields, LoadParseDocumentMeta

    bad = LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename="x.pdf"),
        extracted=LoadParseExtractedFields.model_construct(rate=float("inf")),
        raw_text="x",
        warnings=[],
        field_confidence={},
        context={},
    )
    out = apply_load_parser_mechanical_validation(bad)
    assert out.extracted.rate is None
    assert "invalid_number: rate" in out.warnings


def test_negative_miles_and_weight_rejected() -> None:
    out = apply_load_parser_mechanical_validation(
        _base_response(extracted={"miles": -1, "estimated_weight": -10})
    )
    assert out.extracted.miles is None
    assert out.extracted.estimated_weight is None


def test_customer_rate_not_copied_to_rate() -> None:
    res = _base_response(extracted={"rate": None, "customer_rate": 900.0})
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.rate is None
    assert out.extracted.customer_rate == 900.0


# --- Load reference ---


def test_valid_reference_preserved_and_whitespace_normalized() -> None:
    res = _base_response(extracted={"broker_load_reference": "  3872125-1  "})
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_load_reference == "3872125-1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Load #3872125-1", "3872125-1"),
        ("Load Number: ABC-123", "ABC-123"),
        ("Order # 12345", "12345"),
        ("PO # 34307972", "34307972"),
        ("Confirmation #: ABC-123", "ABC-123"),
    ],
)
def test_load_reference_strips_separator_gated_field_label(raw: str, expected: str) -> None:
    out = apply_load_parser_mechanical_validation(
        _base_response(extracted={"broker_load_reference": raw})
    )
    assert out.extracted.broker_load_reference == expected


@pytest.mark.parametrize(
    "raw",
    ["PO12345", "EL6596031", "ABC-123"],
)
def test_load_reference_preserves_glued_or_unlabeled_identifier(raw: str) -> None:
    out = apply_load_parser_mechanical_validation(
        _base_response(extracted={"broker_load_reference": raw})
    )
    assert out.extracted.broker_load_reference == raw


def test_suspicious_instruction_token_rejected() -> None:
    res = _base_response(extracted={"broker_load_reference": "Information"})
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_load_reference is None


def test_money_like_reference_rejected() -> None:
    res = _base_response(extracted={"broker_load_reference": "1800.00"})
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_load_reference is None


def test_does_not_replace_reference_from_references_list() -> None:
    res = _base_response(
        extracted={
            "broker_load_reference": "Information",
            "references": [{"kind": "load_number", "value": "SHOULD-NOT-BE-PICKED"}],
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.broker_load_reference is None
    assert out.extracted.references[0].value == "SHOULD-NOT-BE-PICKED"


# --- Stops ---


def test_valid_sequences_and_dates_preserved() -> None:
    out = apply_load_parser_mechanical_validation(_base_response())
    assert [s.sequence for s in out.extracted.stops] == [0, 1]
    assert out.extracted.stops[0].appointment_date == "2025-10-28"
    assert out.extracted.stops[0].stop_type == "pickup"
    assert out.extracted.stops[1].stop_type == "delivery"


def test_duplicate_sequence_warning_no_reorder() -> None:
    res = _base_response(
        extracted={
            "stops": [
                {"stop_type": "pickup", "sequence": 2, "facility_name": "A", "appointment_date": "2025-01-01"},
                {"stop_type": "delivery", "sequence": 2, "facility_name": "B", "appointment_date": "2025-01-02"},
            ]
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert [s.facility_name for s in out.extracted.stops] == ["A", "B"]
    assert "duplicate_stop_sequence: 2" in out.warnings


def test_invalid_calendar_date_rejected() -> None:
    res = _base_response(
        extracted={
            "stops": [
                {
                    "stop_type": "pickup",
                    "sequence": 0,
                    "facility_name": "A",
                    "appointment_date": "2026-02-31",
                }
            ]
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.stops[0].appointment_date is None
    assert "invalid_date: stops[0].appointment_date" in out.warnings


def test_leap_day_preserved() -> None:
    res = _base_response(
        extracted={
            "stops": [
                {
                    "stop_type": "pickup",
                    "sequence": 0,
                    "facility_name": "A",
                    "appointment_date": "2024-02-29",
                }
            ]
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.stops[0].appointment_date == "2024-02-29"


def test_does_not_swap_pickup_delivery() -> None:
    res = _base_response()
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.stops[0].stop_type == "pickup"
    assert out.extracted.stops[1].stop_type == "delivery"


def test_appt_prefix_syntactic_normalize() -> None:
    res = _base_response(
        extracted={
            "stops": [
                {
                    "stop_type": "pickup",
                    "sequence": 0,
                    "facility_name": "A",
                    "appointment_date": "2025-01-01",
                    "appointment_time_text": "Appt 08:00-12:00",
                }
            ]
        }
    )
    out = apply_load_parser_mechanical_validation(res)
    assert out.extracted.stops[0].appointment_type == "APPT"
    assert out.extracted.stops[0].appointment_time_text == "08:00-12:00"


# --- Literal presence ---


def test_reference_present_no_warning() -> None:
    out = apply_load_parser_mechanical_validation(
        _base_response(),
        page_texts=["Load #3872125-1 Armstrong"],
    )
    assert "value_not_found_in_source: broker_load_reference" not in out.warnings
    assert out.extracted.broker_load_reference == "3872125-1"


def test_reference_absent_warning_value_unchanged() -> None:
    # Include digits so the token is not rejected by the suspicious-token mechanical rule.
    res = _base_response(
        extracted={"broker_load_reference": "MISSING-REF-99999"},
        raw_text="no matching token here",
    )
    out = apply_load_parser_mechanical_validation(res, page_texts=["no matching token here"])
    assert out.extracted.broker_load_reference == "MISSING-REF-99999"
    assert "value_not_found_in_source: broker_load_reference" in out.warnings


def test_phone_digits_presence() -> None:
    out_ok = apply_load_parser_mechanical_validation(
        _base_response(),
        page_texts=["call 2087518073 today"],
    )
    assert "value_not_found_in_source: broker_contact_phone_snapshot" not in out_ok.warnings

    out_bad = apply_load_parser_mechanical_validation(
        _base_response(extracted={"broker_contact_phone_snapshot": "999-111-2222"}),
        page_texts=["call 2087518073 today"],
    )
    assert "value_not_found_in_source: broker_contact_phone_snapshot" in out_bad.warnings
    assert out_bad.extracted.broker_contact_phone_snapshot == "999-111-2222"


def test_rate_presence_formatted() -> None:
    out = apply_load_parser_mechanical_validation(
        _base_response(extracted={"rate": 1800.0}),
        page_texts=["Total Carrier Pay $1,800.00 USD"],
    )
    assert "value_not_found_in_source: rate" not in out.warnings


# --- Purity / no diagnostics ---


def test_caller_input_not_mutated() -> None:
    res = _base_response(extracted={"broker_name_snapshot": "IK Logistics"})
    before = copy.deepcopy(res.model_dump(mode="json"))
    _ = apply_load_parser_mechanical_validation(res, tenant_identity_exclusion=_exclusion())
    assert res.model_dump(mode="json") == before


def test_module_has_no_forbidden_imports() -> None:
    mod = importlib.import_module("app.services.load_parser_mechanical_validation")
    # Import graph must not pull diagnostics / guardrails / ranking.
    forbidden_modules = {
        "app.services.load_document_parse_diagnostics",
        "app.services.load_document_parse_guardrails",
        "app.services.load_document_parse_reference",
        "app.services.load_document_parse_contact_candidates",
    }
    imported = set(getattr(mod, "__dict__", {}))
    # Also inspect source import lines only.
    src = open(mod.__file__, encoding="utf-8").read()
    import_lines = [
        ln.strip()
        for ln in src.splitlines()
        if ln.strip().startswith("import ") or ln.strip().startswith("from ")
    ]
    blob = "\n".join(import_lines)
    for name in forbidden_modules:
        assert name not in blob, f"forbidden import: {name}"
    for fn in (
        "build_load_document_parse_diagnostics",
        "rank_reference_candidates",
        "merge_ranked_references_into_extracted",
    ):
        assert fn not in blob, f"forbidden import symbol: {fn}"
    _ = imported  # silence lint; graph checked via source import lines


def test_strips_diagnostics_from_context() -> None:
    res = _base_response()
    payload = res.model_dump(mode="json")
    payload["context"] = {
        "parse_path": "test",
        "parse_diagnostics": {"role_hint": "broker_context"},
        "contact_candidates": [{"role": "broker_party"}],
    }
    res2 = LoadDocumentParseResponse.model_validate(payload)
    out = apply_load_parser_mechanical_validation(res2)
    assert "parse_diagnostics" not in out.context
    assert "contact_candidates" not in out.context
    assert out.context.get("parse_path") == "test"


def test_drops_invalid_reference_items() -> None:
    from app.services.load_parser_mechanical_validation import _sanitize_references

    extracted, warnings = _sanitize_references(
        {
            "references": [
                {"kind": "po", "value": "OK"},
                {"kind": "", "value": "x"},
                {"kind": "po", "value": ""},
                {"kind": "po"},
            ]
        }
    )
    assert extracted["references"] == [{"kind": "po", "value": "OK"}]
    assert any("invalid_reference_item" in w for w in warnings)
