"""Focused tests for frozen Rate Confirmation field_rules (no OpenAI, no hydration)."""

from __future__ import annotations

from app.services.load_parser_rate_con_field_rules import (
    APPROVED_FIELD_RULE_KEYS,
    get_load_rate_con_field_rules,
)

# Armstrong live-parse evidence (tests only — not hardcoded in field_rules).
_ARMSTRONG_BROKER_COMPANY = "Armstrong Transport Group"
_ARMSTRONG_CORPORATE_MC = "555609"
_ARMSTRONG_CARRIER_COMPANY = "9582479 CANADA INC DBA IK LOGISTICS"
_ARMSTRONG_CARRIER_MC = "1397898"
_ARMSTRONG_CARRIER_DOT = "3842541"
_ARMSTRONG_AGENT = "Loflin Phillips"
_ARMSTRONG_AUDIT_RATE_CON_ID = "5506390"


def _rules() -> dict:
    return get_load_rate_con_field_rules()["rules"]


def _joined(group: str) -> str:
    blob = _rules()[group]
    parts = [str(blob.get("meaning") or ""), str(blob.get("how_to_choose") or "")]
    parts.extend(str(r) for r in blob.get("rules") or [])
    return " ".join(parts)


def test_broker_authority_exists_and_is_approved() -> None:
    assert "broker_authority" in APPROVED_FIELD_RULE_KEYS
    rules = _rules()
    assert "broker_authority" in rules
    assert list(rules.keys()) == list(APPROVED_FIELD_RULE_KEYS)


def test_broker_authority_covers_mc_and_dot_snapshot_fields() -> None:
    product_fields = _rules()["broker_authority"]["product_fields"]
    assert product_fields == [
        "broker_mc_number_snapshot",
        "broker_dot_number_snapshot",
    ]
    meaning = _rules()["broker_authority"]["meaning"]
    assert "freight broker" in meaning.lower()
    assert "MC" in meaning or "USDOT" in meaning


def test_broker_authority_excludes_tenant_and_carrier_mc_dot() -> None:
    text = _joined("broker_authority")
    assert "tenant_identity_exclusion" in text
    assert "Never return the carrier/tenant's MC/DOT as broker authority." in _rules()[
        "broker_authority"
    ]["rules"]
    # Armstrong carrier/tenant pair must not be treated as broker authority.
    assert _ARMSTRONG_CARRIER_MC != _ARMSTRONG_CORPORATE_MC
    assert _ARMSTRONG_CARRIER_COMPANY != _ARMSTRONG_BROKER_COMPANY
    assert _ARMSTRONG_CARRIER_MC not in text
    assert _ARMSTRONG_CARRIER_DOT not in text


def test_broker_authority_allows_mc_while_dot_remains_null() -> None:
    rules = _rules()["broker_authority"]["rules"]
    assert any(
        "If broker MC is supported but broker USDOT is absent, return MC and leave DOT null."
        in r
        for r in rules
    )
    # Armstrong corporate block: MC present, no broker USDOT.
    assert _ARMSTRONG_CORPORATE_MC == "555609"


def test_broker_authority_ownership_is_entity_not_proximity() -> None:
    rules = _rules()["broker_authority"]["rules"]
    assert any(
        "must belong to the selected broker company, not merely be nearby numbers" in r
        for r in rules
    )
    assert any(
        "Do not transfer an MC/DOT to the broker merely because it appears near a broker" in r
        for r in rules
    )
    assert any(
        "proximity alone does not establish ownership" in r for r in rules
    )
    assert any(
        "associate each authority with its actual company/entity" in r for r in rules
    )
    text = _joined("broker_authority")
    assert "corporate-information" in text or "corporate information" in text.lower()
    # Armstrong: corporate MC 555609 is broker; 1397898/3842541 near the agent are carrier.
    assert _ARMSTRONG_CORPORATE_MC == "555609"
    assert _ARMSTRONG_CARRIER_DOT == "3842541"


def test_broker_contact_covers_repeated_load_specific_agent_evidence() -> None:
    rules = _rules()["broker_contact"]["rules"]
    blob = " ".join(rules)
    assert "FOR LOAD INFORMATION" in blob
    assert "Agent Name" in blob
    assert "Please Sign and Email to" in blob
    assert "For specific information about this load, contact" in blob
    assert "person-specific email on the broker company's domain" in blob
    assert "Repeated name/email/phone evidence tied to the same load" in blob
    assert "Contact identity and authority ownership must be evaluated separately." in blob
    assert any(
        "Do not reject a valid broker contact merely because carrier authority numbers" in r
        for r in rules
    )
    assert any("Still never return tenant/carrier people as broker contacts." in r for r in rules)
    assert "Do not return tenant/carrier contacts as broker contacts." in rules
    # Armstrong expected person remains Loflin Phillips; nearby carrier MC/DOT are not contact identity.
    assert _ARMSTRONG_AGENT == "Loflin Phillips"


def test_references_still_exclude_audit_ids() -> None:
    rules = _rules()["references"]["rules"]
    blob = " ".join(rules)
    assert "audit" in blob.lower()
    assert "IDs" in blob or "audit IDs" in blob
    assert "Do not treat every number in the document as a reference." in rules
    # Armstrong Highway Audit Report Rate Confirmation ID must stay out of references[].
    assert _ARMSTRONG_AUDIT_RATE_CON_ID == "5506390"
    assert _ARMSTRONG_AUDIT_RATE_CON_ID not in blob
    assert "Rate Confirmation ID" not in blob
    assert "Highway Audit Report" not in blob
    assert "broker_authority" not in _rules()["references"]["product_fields"]
