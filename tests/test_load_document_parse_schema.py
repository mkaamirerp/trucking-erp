"""Parse-response schema semantics for Load / Rate Confirmation (no OpenAI)."""

from __future__ import annotations

import json

from app.schemas.load_document_parse import LoadParseExtractedFields

_ARMSTRONG_VALUES = (
    "Armstrong Transport Group",
    "Loflin Phillips",
    "877-240-1181",
    "208-751-8073",
    "l.phillips@armstrongtransport.com",
    "carriers@armstrongtransport.com",
    "armstrongtransport.com",
)


def _field_desc(name: str) -> str:
    info = LoadParseExtractedFields.model_fields[name]
    return str(info.description or "")


def _schema_blob() -> str:
    return json.dumps(LoadParseExtractedFields.model_json_schema())


def test_broker_phone_snapshot_exists_and_is_optional() -> None:
    fields = LoadParseExtractedFields.model_fields
    assert "broker_phone_snapshot" in fields
    assert fields["broker_phone_snapshot"].is_required() is False
    empty = LoadParseExtractedFields()
    assert empty.broker_phone_snapshot is None


def test_schema_distinguishes_company_phone_from_agent_direct_phone() -> None:
    company = _field_desc("broker_phone_snapshot").casefold()
    agent = _field_desc("broker_contact_phone_snapshot").casefold()
    assert "company" in company or "corporate" in company
    assert "main" in company or "corporate" in company
    assert "named agent's direct phone" in company or "not the named agent" in company
    assert "direct phone" in agent
    assert "selected named broker contact" in agent
    assert "corporate/main/general" in agent
    assert "null" in agent


def test_schema_contact_phone_and_email_are_selected_person_owned() -> None:
    phone = _field_desc("broker_contact_phone_snapshot").casefold()
    email = _field_desc("broker_contact_email_snapshot").casefold()
    name = _field_desc("broker_contact_name_snapshot").casefold()
    company = _field_desc("broker_name_snapshot").casefold()
    assert "individual" in name or "agent" in name
    assert "company/entity" in company or "not the individual agent" in company
    assert "selected named broker contact" in phone
    assert "person-owned direct phone" in phone
    assert "selected named broker contact" in email
    assert "person-owned email" in email


def test_schema_excludes_generic_company_mailboxes_from_contact_email() -> None:
    email = _field_desc("broker_contact_email_snapshot").casefold()
    for local in (
        "carriers@",
        "dispatch@",
        "info@",
        "operations@",
        "billing@",
        "accounting@",
        "support@",
    ):
        assert local in email


def test_parse_schema_text_contains_no_armstrong_values() -> None:
    blob = _schema_blob()
    for needle in _ARMSTRONG_VALUES:
        assert needle not in blob
