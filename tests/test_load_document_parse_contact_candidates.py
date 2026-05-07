"""Generic section/contact_candidate behavior (no broker-specific hardcoding)."""

from __future__ import annotations

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse_diagnostics import build_load_document_parse_diagnostics
from app.services.load_document_parse_guardrails import apply_guarded_load_document_repairs


def _roles_by_value_kind(diag: dict) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for c in diag.get("contact_candidates") or []:
        if not isinstance(c, dict):
            continue
        kind = str(c.get("kind") or "")
        val = str(c.get("value") or "").strip()
        role = str(c.get("role") or "")
        out[(kind, val.casefold())] = role
    return out


def test_mixed_carrier_and_contact_headers_on_one_line_do_not_merge_roles() -> None:
    text = """
CARRIER INFORMATION CONTACT INFORMATION
Alex Carrier 555-100-2002 alex@hotmail.com    Sam Rep 555-300-4004 sam.rep@loadbrokersample.com
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text,
        page_texts=[text],
        filename="dualhdr.pdf",
        extraction_method="test",
    )
    rk = _roles_by_value_kind(diag)
    assert rk[("email", "alex@hotmail.com")] == "carrier_party"
    assert rk[("email", "sam.rep@loadbrokersample.com")] == "broker_party"
    alex_row = next(c for c in diag["contact_candidates"] if c.get("value") == "alex@hotmail.com")
    assert alex_row["section_context"] == ["carrier_information"]


def test_carrier_email_cannot_populate_broker_contact_email() -> None:
    text = """
CONTACT INFORMATION
Acct Rep 555-400-5006 rep@loadbrokersample.com
CARRIER CONTACT
Sam Driver 555-900-8007 sam.driver@hotmail.com
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text, page_texts=[text], filename="t.pdf", extraction_method="test"
    )
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "t.pdf"},
            "extracted": {
                "broker_contact_email_snapshot": "sam.driver@hotmail.com",
                "references": [],
                "stops": [],
            },
            "raw_text": text,
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }
    )
    out = apply_guarded_load_document_repairs(base, diagnostics=diag)
    assert out.extracted.broker_contact_email_snapshot is None


def test_valid_broker_contact_survives_guardrails() -> None:
    text = """
CONTACT INFORMATION
Acct Rep 555-400-5006 rep@loadbrokersample.com
CARRIER CONTACT
Sam Driver 555-900-8007 sam.driver@hotmail.com
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text, page_texts=[text], filename="t.pdf", extraction_method="test"
    )
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "t.pdf"},
            "extracted": {
                "broker_contact_email_snapshot": "rep@loadbrokersample.com",
                "broker_contact_phone_snapshot": "555-400-5006",
                "references": [],
                "stops": [],
            },
            "raw_text": text,
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }
    )
    out = apply_guarded_load_document_repairs(base, diagnostics=diag)
    assert out.extracted.broker_contact_email_snapshot == "rep@loadbrokersample.com"
    assert "5554005006" in (out.extracted.broker_contact_phone_snapshot or "").replace("-", "")


def test_email_cannot_become_contact_name() -> None:
    out = apply_guarded_load_document_repairs(
        LoadDocumentParseResponse.model_validate(
            {
                "document": {"filename": "x.pdf"},
                "extracted": {"broker_contact_name_snapshot": "rep@loadbrokersample.com", "references": [], "stops": []},
                "raw_text": "",
                "warnings": [],
                "field_confidence": {},
                "context": {},
            }
        ),
        diagnostics={"contact_candidates": []},
    )
    assert out.extracted.broker_contact_name_snapshot is None


def test_phone_cannot_become_contact_name() -> None:
    out = apply_guarded_load_document_repairs(
        LoadDocumentParseResponse.model_validate(
            {
                "document": {"filename": "x.pdf"},
                "extracted": {"broker_contact_name_snapshot": "555-111-2222", "references": [], "stops": []},
                "raw_text": "",
                "warnings": [],
                "field_confidence": {},
                "context": {},
            }
        ),
        diagnostics={"contact_candidates": []},
    )
    assert out.extracted.broker_contact_name_snapshot is None


def test_payment_paperwork_email_not_broker_contact() -> None:
    text = """
PAYMENT STATUS QUESTIONS
Upload paperwork to carrierpaperwork@paymentsdesk.example.com
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text, page_texts=[text], filename="pay.pdf", extraction_method="test"
    )
    roles = {c["value"].casefold(): c["role"] for c in diag["contact_candidates"] if c.get("kind") == "email"}
    assert roles["carrierpaperwork@paymentsdesk.example.com"] == "payment_paperwork_party"

    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "pay.pdf"},
            "extracted": {"broker_contact_email_snapshot": "carrierpaperwork@paymentsdesk.example.com", "references": [], "stops": []},
            "raw_text": text,
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }
    )
    out = apply_guarded_load_document_repairs(base, diagnostics=diag)
    assert out.extracted.broker_contact_email_snapshot is None


def test_shipper_location_email_not_broker_contact() -> None:
    text = """
STOP DETAIL
Consignee contact facilitydock@warehouseops.example.com
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text, page_texts=[text], filename="stop.pdf", extraction_method="test"
    )
    roles = {c["value"].casefold(): c["role"] for c in diag["contact_candidates"] if c.get("kind") == "email"}
    assert roles["facilitydock@warehouseops.example.com"] == "shipper_receiver_party"

    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "stop.pdf"},
            "extracted": {"broker_contact_email_snapshot": "facilitydock@warehouseops.example.com", "references": [], "stops": []},
            "raw_text": text,
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }
    )
    out = apply_guarded_load_document_repairs(base, diagnostics=diag)
    assert out.extracted.broker_contact_email_snapshot is None


def test_secondary_broker_email_not_final_when_primary_exists() -> None:
    text = """
CONTACT INFORMATION
Pat Ops 704-555-1000 pat.ops@loadbrokersample.com
After Hours 980-555-2000 lane-tracking@loadbrokersample.com
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text, page_texts=[text], filename="tier.pdf", extraction_method="test"
    )
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "tier.pdf"},
            "extracted": {
                "broker_contact_email_snapshot": "lane-tracking@loadbrokersample.com",
                "references": [],
                "stops": [],
            },
            "raw_text": text,
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }
    )
    out = apply_guarded_load_document_repairs(base, diagnostics=diag)
    assert out.extracted.broker_contact_email_snapshot == "pat.ops@loadbrokersample.com"


def test_missing_broker_contact_stays_null() -> None:
    out = apply_guarded_load_document_repairs(
        LoadDocumentParseResponse.model_validate(
            {
                "document": {"filename": "x.pdf"},
                "extracted": {
                    "broker_contact_name_snapshot": None,
                    "broker_contact_email_snapshot": None,
                    "broker_contact_phone_snapshot": None,
                    "references": [],
                    "stops": [],
                },
                "raw_text": "",
                "warnings": [],
                "field_confidence": {},
                "context": {},
            }
        ),
        diagnostics={"contact_candidates": []},
    )
    assert out.extracted.broker_contact_email_snapshot is None
