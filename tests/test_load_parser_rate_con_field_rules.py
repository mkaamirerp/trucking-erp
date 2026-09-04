"""Focused tests for frozen Rate Confirmation field_rules (no OpenAI, no hydration)."""

from __future__ import annotations

import json

from app.services.load_parser_rate_con_field_rules import (
    APPROVED_FIELD_RULE_KEYS,
    LOAD_RATE_CON_FIELD_RULES,
    get_load_rate_con_field_rules,
)

# Armstrong live-parse evidence (tests only — not hardcoded as tenant/broker identity).
_ARMSTRONG_BROKER_COMPANY = "Armstrong Transport Group"
_ARMSTRONG_CORPORATE_MC = "555609"
_ARMSTRONG_CARRIER_COMPANY = "9582479 CANADA INC DBA IK LOGISTICS"
_ARMSTRONG_CARRIER_MC = "1397898"
_ARMSTRONG_CARRIER_DOT = "3842541"
_ARMSTRONG_AGENT = "Loflin Phillips"
_ARMSTRONG_CARRIER_ATTN = "Imran Khan"
_ARMSTRONG_CARRIER_PHONE = "647-248-4699"
_ARMSTRONG_CARRIER_EMAIL = "khanahmad73@hotmail.com"
_ARMSTRONG_AUDIT_RATE_CON_ID = "5506390"
_ARMSTRONG_CORPORATE_PHONE = "877-240-1181"
_ARMSTRONG_AGENT_PHONE = "208-751-8073"
_ARMSTRONG_AGENT_EMAIL = "l.phillip@armstrongtransport.com"
_ARMSTRONG_COMPANY_EMAIL = "carriers@armstrongtransport.com"
_ARMSTRONG_LOAD_REF = "3872125-1"
_ARMSTRONG_LOAD_REF_WITH_LABEL = "Load #3872125-1"

_EXPECTED_KEYS = (
    "broker_company",
    "broker_authority",
    "broker_agent",
    "principal_load_identifier",
    "rate_broker_pay",
    "customer_rate_guardrail",
    "freight_mode",
    "equipment_description",
    "trailer_body_type",
    "trailer_length",
    "commodity",
    "estimated_weight",
    "temperature_requirement",
    "miles",
    "stops",
    "pickup_semantics",
    "delivery_semantics",
    "appointment_date_time",
    "references",
)


def _rules() -> dict:
    return get_load_rate_con_field_rules()["rules"]


def _production_rules_blob() -> str:
    return json.dumps(LOAD_RATE_CON_FIELD_RULES)


def test_canonical_contract_shape() -> None:
    fr = get_load_rate_con_field_rules()
    assert fr["profile"] == "rate_confirmation"
    assert fr["version"] == "load_rate_con_field_rules_v2_full_canonical_semantics"
    assert isinstance(fr["global_rules"], list) and len(fr["global_rules"]) == 9
    assert APPROVED_FIELD_RULE_KEYS == _EXPECTED_KEYS
    assert list(_rules().keys()) == list(_EXPECTED_KEYS)


def test_semantic_product_fields() -> None:
    rules = _rules()
    assert rules["broker_company"]["product_fields"] == [
        "broker_company.name",
        "broker_company.main_phone",
    ]
    assert rules["broker_authority"]["product_fields"] == [
        "broker_company.mc_number",
        "broker_company.dot_number",
    ]
    assert rules["broker_agent"]["product_fields"] == [
        "broker_agent.name",
        "broker_agent.direct_phone",
        "broker_agent.email",
    ]
    assert rules["principal_load_identifier"]["product_fields"] == [
        "principal_load_identifier"
    ]
    assert rules["freight_mode"]["product_fields"] == ["freight_mode"]
    assert rules["equipment_description"]["product_fields"] == ["equipment.description"]
    assert rules["trailer_body_type"]["product_fields"] == ["equipment.trailer_body_type"]
    assert rules["trailer_length"]["product_fields"] == ["equipment.trailer_length"]
    assert rules["commodity"]["product_fields"] == ["commodity"]
    assert rules["estimated_weight"]["product_fields"] == ["estimated_weight"]
    assert rules["temperature_requirement"]["product_fields"] == ["temperature_requirement"]
    assert rules["miles"]["product_fields"] == ["miles"]


def test_rate_is_primary_freight_not_total_compensation() -> None:
    group = _rules()["rate_broker_pay"]
    blob = json.dumps(group)
    assert "agreed freight rate only" in group["core_principle"]
    assert "Do not automatically trust a field labeled Total Carrier Pay" in blob
    assert group["output"]["include_accessorials"] is False
    assert group["output"]["calculate_net_pay"] is False


def test_principal_load_identifier_uses_strong_labels() -> None:
    group = _rules()["principal_load_identifier"]
    labels = group["strong_labels"]
    assert "Load #" in labels
    assert "Broker Load #" in labels
    assert "PO #" in labels
    blob = json.dumps(group)
    assert "broker_load_reference" not in blob
    assert _ARMSTRONG_LOAD_REF not in blob
    assert _ARMSTRONG_LOAD_REF_WITH_LABEL not in blob


def test_broker_agent_cohesion_and_generic_mailbox() -> None:
    blob = json.dumps(_rules()["broker_agent"])
    assert "broker_agent_contact_cohesion" in blob
    assert "carriers@" in blob
    assert "FOR LOAD INFORMATION" in blob
    assert "broker_contact_phone_snapshot" not in blob
    assert _ARMSTRONG_AGENT not in blob
    assert _ARMSTRONG_AGENT_PHONE not in blob
    assert _ARMSTRONG_AGENT_EMAIL not in blob


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
    assert _ARMSTRONG_CORPORATE_MC not in blob
    assert _ARMSTRONG_CARRIER_MC not in blob
    assert _ARMSTRONG_CARRIER_DOT not in blob
    assert _ARMSTRONG_AUDIT_RATE_CON_ID not in blob
    assert _ARMSTRONG_CARRIER_ATTN not in blob
    assert _ARMSTRONG_CARRIER_PHONE not in blob
    assert _ARMSTRONG_CARRIER_EMAIL not in blob


def test_broker_agent_carrier_owned_tuple_is_not_broker_agent() -> None:
    agent = _rules()["broker_agent"]
    blob = json.dumps(agent)
    prec = agent["ownership_precedence"]
    assert "carrier contact, not a broker_agent" in prec["carrier_owned_person_is_not_broker_agent"]
    assert "Do not take a person's name, phone, or email from a carrier-owned block" in prec[
        "do_not_emit_carrier_tuple_as_broker_agent"
    ]
    assert "reject_carrier_owned_people" in blob
    assert "person in a Carrier Name, Carrier Information, Carrier Signature, carrier Attn" in blob
    assert "A cohesive name-phone-email tuple inside a Carrier Name" in blob


def test_broker_agent_ownership_outranks_name_phone_email_cohesion() -> None:
    agent = _rules()["broker_agent"]
    prec = agent["ownership_precedence"]
    cohesion = agent["broker_agent_name"]["broker_agent_contact_cohesion"]
    assert prec["priority"] == "Entity and role ownership outrank adjacency and contact-tuple cohesion."
    for label in (
        "Carrier Name",
        "Carrier Information",
        "Carrier Signature",
        "carrier Attn block",
    ):
        assert label in prec["carrier_owned_blocks"]
    assert cohesion["applies_only_after"] == "entity_role_ownership"
    assert "does not override carrier ownership" in cohesion["rule"]
    assert any("cleanest name-phone-email tuple" in item for item in cohesion["must_not_do"])
    assert any("carrier-owned block and emit it as broker_agent" in item for item in cohesion["must_not_do"])
    assert "name-phone-email cohesion" in json.dumps(agent["flattened_pdf_ownership_rules"])


def test_broker_agent_positive_broker_owned_labels_remain() -> None:
    evidence = _rules()["broker_agent"]["broker_agent_name"]["positive_broker_person_evidence"]
    labels = evidence["labels"]
    for label in (
        "Agent Name",
        "Broker Representative",
        "Broker Contact",
        "For Load Information",
        "Please contact",
        "Please sign and email to",
    ):
        assert label in labels
    assert "belongs to the broker rather than the carrier" in evidence["rule"]
    assert "keep them together as one broker_agent" in evidence["keep_broker_owned_tuple_together"]
    assert "Do not pull a replacement phone or email from a different corporate or carrier block" in evidence[
        "keep_broker_owned_tuple_together"
    ]
    strong = json.dumps(_rules()["broker_agent"]["broker_agent_name"]["strong_evidence"])
    assert "Agent Name in a broker-owned section" in strong
    assert "For Load Information" in strong


def test_broker_authority_binds_corporate_mc_to_selected_broker() -> None:
    auth = _rules()["broker_authority"]
    prec = auth["ownership_precedence"]
    steps = {item["action"]: item["rule"] for item in auth["before_populating"]}
    assert "Corporate Information" in prec["bind_to_selected_broker"]
    assert "belongs to that broker when ownership is clear" in prec["bind_to_selected_broker"]
    assert "bind_selected_broker_corporate_authority" in steps
    assert "Corporate Information" in steps["bind_selected_broker_corporate_authority"]
    assert "issuer/header company block" in steps["bind_selected_broker_corporate_authority"]


def test_broker_authority_carrier_mc_does_not_make_broker_authority_ambiguous() -> None:
    auth = _rules()["broker_authority"]
    prec = auth["ownership_precedence"]
    steps = {item["action"]: item["rule"] for item in auth["before_populating"]}
    blob = json.dumps(auth["rules"])
    assert "Carrier Name" in prec["carrier_authority_is_separate"]
    assert "not a reason to null the selected broker's authority" in prec["carrier_authority_is_separate"]
    assert "isolate_carrier_authority" in steps
    assert "must not create ambiguity about the selected broker's authority" in steps["isolate_carrier_authority"]
    assert "presence of carrier MC/DOT does not make selected-broker authority ambiguous" in blob


def test_broker_authority_multiple_clear_authorities_must_not_force_null() -> None:
    auth = _rules()["broker_authority"]
    prec = auth["ownership_precedence"]
    blob = json.dumps(auth["rules"])
    assert "Do not return null merely because multiple authority numbers exist" in prec["multiple_authorities"]
    assert "ownership itself is genuinely ambiguous" in prec["multiple_authorities"]
    assert "Do not return null merely because multiple authorities exist on the page" in blob
    assert "when entity ownership is clearly distinguishable" in blob


def test_field_rules_factory_is_independent_copy() -> None:
    a = get_load_rate_con_field_rules()
    b = get_load_rate_con_field_rules()
    a["rules"]["broker_company"]["meaning"] = "MUTATED"
    assert b["rules"]["broker_company"]["meaning"] != "MUTATED"
    assert LOAD_RATE_CON_FIELD_RULES["rules"]["broker_company"]["meaning"] != "MUTATED"
