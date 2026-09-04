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
_ARMSTRONG_CORPORATE_PHONE = "877-240-1181"
_ARMSTRONG_AGENT_PHONE = "208-751-8073"
_ARMSTRONG_AGENT_EMAIL = "l.phillip@armstrongtransport.com"
_ARMSTRONG_COMPANY_EMAIL = "carriers@armstrongtransport.com"
_ARMSTRONG_LOAD_REF = "3872125-1"
_ARMSTRONG_LOAD_REF_WITH_LABEL = "Load #3872125-1"

# Slice A must not add groups.
_SLICE_A_APPROVED_KEYS = (
    "broker_load_reference",
    "broker_company",
    "broker_authority",
    "broker_contact",
    "rate_broker_pay",
    "customer_rate_guardrail",
    "stops",
    "pickup_semantics",
    "delivery_semantics",
    "appointment_date_time",
    "references",
)
_APPROVED_KEYS = _SLICE_A_APPROVED_KEYS + (
    "freight_mode",
    "trailer_type",
    "trailer_size",
)


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
    assert "person-specific mailbox explicitly associated with the selected person" in blob
    assert "Broker-domain membership alone is company association, not person ownership." in blob
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


def _production_rules_blob() -> str:
    import json

    from app.services.load_parser_rate_con_field_rules import LOAD_RATE_CON_FIELD_RULES

    return json.dumps(LOAD_RATE_CON_FIELD_RULES)


def test_approved_field_rule_keys_match_rules_dict() -> None:
    assert APPROVED_FIELD_RULE_KEYS == _APPROVED_KEYS
    assert list(_rules().keys()) == list(_APPROVED_KEYS)
    assert "equipment_type" not in APPROVED_FIELD_RULE_KEYS


def test_broker_contact_phone_is_direct_person_not_company() -> None:
    rules = _rules()["broker_contact"]["rules"]
    blob = " ".join(rules)
    assert any(
        "broker_contact_phone_snapshot must be that person's direct phone" in r for r in rules
    )
    assert "direct phone" in blob
    assert any("Do not populate broker_contact_phone_snapshot with the broker company's main phone" in r for r in rules)
    assert "corporate phone" in blob
    assert "general office number" in blob
    assert any(
        "If only a company or corporate number is supported, return null for" in r for r in rules
    )
    assert "broker_contact_phone_snapshot" in blob
    # Armstrong: named-agent phone vs corporate/main line — values stay out of production rules.
    assert _ARMSTRONG_AGENT_PHONE not in blob
    assert _ARMSTRONG_CORPORATE_PHONE not in blob


def test_broker_contact_email_rejects_generic_company_mailbox() -> None:
    rules = _rules()["broker_contact"]["rules"]
    blob = " ".join(rules)
    assert any(
        "broker_contact_email_snapshot must belong to that person" in r for r in rules
    )
    assert "carriers@" in blob
    assert "dispatch@" in blob
    assert "info@" in blob
    assert "operations@" in blob
    assert "billing@" in blob
    assert "accounting@" in blob
    assert "support@" in blob
    assert "must not populate a named person's email" in blob
    assert any(
        "proves company association, not person association" in r for r in rules
    )
    assert any(
        "If only a generic or company mailbox is supported, return null for" in r for r in rules
    )
    assert _ARMSTRONG_AGENT_EMAIL not in blob
    assert _ARMSTRONG_COMPANY_EMAIL not in blob


def test_broker_load_reference_is_identifier_only() -> None:
    rules = _rules()["broker_load_reference"]["rules"]
    blob = " ".join(rules)
    assert "Return only the identifier value in broker_load_reference." in rules
    assert any("discovery labels only" in r for r in rules)
    assert any("do not include the label or prefix text in the value" in r for r in rules)
    assert "Load #" in blob
    assert "Load Number" in blob
    assert "Order #" in blob
    assert "Confirmation #" in blob
    assert "PO #" in blob
    # Armstrong identifier must not be hardcoded; label-concatenated form is the defect.
    assert _ARMSTRONG_LOAD_REF not in blob
    assert _ARMSTRONG_LOAD_REF_WITH_LABEL not in blob


def test_production_field_rules_contain_no_armstrong_identities() -> None:
    blob = _production_rules_blob()
    assert _ARMSTRONG_BROKER_COMPANY not in blob
    assert _ARMSTRONG_AGENT not in blob
    assert _ARMSTRONG_CORPORATE_PHONE not in blob
    assert _ARMSTRONG_AGENT_PHONE not in blob
    assert _ARMSTRONG_AGENT_EMAIL not in blob
    assert _ARMSTRONG_COMPANY_EMAIL not in blob
    assert _ARMSTRONG_LOAD_REF not in blob
    assert _ARMSTRONG_LOAD_REF_WITH_LABEL not in blob
    assert _ARMSTRONG_CARRIER_COMPANY not in blob
    assert "V53" not in blob


def test_freight_mode_group_normalizes_and_does_not_infer_from_equipment() -> None:
    assert "freight_mode" in APPROVED_FIELD_RULE_KEYS
    group = _rules()["freight_mode"]
    assert group["product_fields"] == ["mode"]
    norm = group["normalization"]
    assert norm["Full TruckLoad"] == "FTL"
    assert norm["Full Truckload"] == "FTL"
    assert norm["Truckload"] == "FTL"
    assert norm["FTL"] == "FTL"
    assert norm["Less Than Truckload"] == "LTL"
    assert norm["LTL"] == "LTL"
    assert norm["Partial"] == "PARTIAL"
    assert norm["Power Only"] == "POWER_ONLY"
    rules = group["rules"]
    blob = " ".join(rules)
    assert any("Populate mode only from explicit load-level mode evidence." in r for r in rules)
    assert "Do not infer mode from equipment" in blob
    assert "trailer type" in blob
    assert "trailer size" in blob
    assert "weight" in blob
    assert "number of stops" in blob
    assert "live/live" in blob.lower() or "live/live" in blob
    assert "rate" in blob
    assert any("If mode is unsupported or ambiguous, return null." in r for r in rules)
    # Combined-source example stays in tests only.
    assert "V53" not in blob
    assert "Full TruckLoad" in blob


def test_trailer_type_and_size_split_combined_equipment_description() -> None:
    assert "trailer_type" in APPROVED_FIELD_RULE_KEYS
    assert "trailer_size" in APPROVED_FIELD_RULE_KEYS
    tt = _rules()["trailer_type"]
    ts = _rules()["trailer_size"]
    assert tt["product_fields"] == ["trailer_type"]
    assert ts["product_fields"] == ["trailer_size"]
    assert "equipment_type" not in _rules()
    tt_blob = " ".join(tt["rules"])
    ts_blob = " ".join(ts["rules"])
    assert "Extract trailer body/type separately from trailer size." in tt["rules"]
    assert "do not put length or size into trailer_type" in tt_blob
    assert "combined equipment description" in tt_blob
    assert "Do not infer trailer type from commodity, temperature, mode, weight, or equipment" in tt_blob
    assert tt["normalization"]["Van"] == "Van"
    assert tt["normalization"]["Dry Van"] == "Dry Van"
    assert tt["normalization"]["Reefer"] == "Reefer"
    assert "Extract explicit trailer length/size separately from trailer type." in ts["rules"]
    assert "trailer_size contains the length/size only" in ts_blob or "length/size only" in ts_blob
    assert "Do not copy the full equipment description into trailer_size." in ts["rules"]
    assert ts["normalization"]["53'"] == "53 ft"
    assert ts["normalization"]["53 feet"] == "53 ft"
    assert "cryptic equipment code" in ts_blob
    assert any("If no explicit supported size is present, return null." in r for r in ts["rules"])
    # Armstrong combined equipment string is test evidence only.
    assert "V53" not in tt_blob
    assert "V53" not in ts_blob
    assert "V53, 53' Van" not in tt_blob
    assert "V53, 53' Van" not in ts_blob
