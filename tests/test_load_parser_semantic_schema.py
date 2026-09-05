"""OpenAI semantic extraction schema + product translator (no OpenAI call)."""

from __future__ import annotations

import json

from app.schemas.load_document_parse import LoadDocumentParseResponse, LoadParseExtractedFields
from app.schemas.load_document_parse_semantic import (
    ParseDocumentSemanticModelOutput,
    SemanticExtractedFields,
)
from app.services.load_parser_mechanical_validation import apply_load_parser_mechanical_validation
from app.services.load_parser_openai_handoff_v2 import (
    build_load_rate_con_openai_handoff_v2_payload,
    build_proposed_openai_request_body_v2,
)
from app.services.load_parser_rate_con_field_rules import (
    LOAD_RATE_CON_FIELD_RULES,
    get_load_rate_con_field_rules,
)
from app.services.load_parser_semantic_to_product import map_semantic_extracted_to_product

_AFFECTED_STORAGE_NAMES = (
    "broker_name_snapshot",
    "broker_phone_snapshot",
    "broker_contact_name_snapshot",
    "broker_contact_phone_snapshot",
    "broker_contact_email_snapshot",
    "broker_load_reference",
    "broker_mc_number_snapshot",
    "broker_dot_number_snapshot",
    "equipment_type",
    "trailer_type",
    "trailer_size",
)

_ARMSTRONG_NEEDLES = (
    "Armstrong Transport Group",
    "Loflin Phillips",
    "877-240-1181",
    "208-751-8073",
    "l.phillip@armstrongtransport.com",
    "carriers@armstrongtransport.com",
    "3872125-1",
    "Load #3872125-1",
)


def _schema() -> dict:
    return ParseDocumentSemanticModelOutput.model_json_schema()


def _defs() -> dict:
    return _schema().get("$defs") or {}


def _extracted_schema() -> dict:
    schema = _schema()
    node = schema["properties"]["extracted"]
    if "$ref" in node:
        return _defs()[node["$ref"].split("/")[-1]]
    return node


def _nested_props(def_name: str) -> dict:
    return _defs()[def_name]["properties"]


def test_semantic_schema_contains_required_structural_objects() -> None:
    extracted = _extracted_schema()
    props = extracted["properties"]
    assert "broker_company" in props
    assert "broker_agent" in props
    assert "principal_load_identifier" in props
    assert "freight_mode" in props
    assert "equipment" in props
    required = set(extracted.get("required") or [])
    assert {"broker_company", "broker_agent", "equipment"} <= required


def test_broker_agent_children() -> None:
    props = _nested_props("BrokerAgent")
    assert set(props) >= {"name", "direct_phone", "email"}
    required = _defs()["BrokerAgent"].get("required") or []
    assert required == []


def test_broker_company_children() -> None:
    props = _nested_props("BrokerCompany")
    assert set(props) >= {"name", "main_phone", "mc_number", "dot_number"}
    required = _defs()["BrokerCompany"].get("required") or []
    assert required == []


def test_equipment_children() -> None:
    props = _nested_props("EquipmentAssignment")
    assert set(props) >= {"description", "trailer_body_type", "trailer_length"}
    required = _defs()["EquipmentAssignment"].get("required") or []
    assert required == []


def test_affected_storage_names_absent_from_openai_semantic_schema() -> None:
    extracted = _extracted_schema()
    blob = json.dumps(extracted)
    for name in _AFFECTED_STORAGE_NAMES:
        assert name not in extracted["properties"]
        assert f'"{name}"' not in blob
    assert "mode" not in extracted["properties"]
    assert "Snapshot" not in blob


def test_translator_maps_every_semantic_field_to_product() -> None:
    product = map_semantic_extracted_to_product(
        {
            "broker_company": {
                "name": "Acme Broker LLC",
                "main_phone": "800-555-0100",
                "mc_number": "123456",
                "dot_number": "654321",
            },
            "broker_agent": {
                "name": "Jane Agent",
                "direct_phone": "208-555-0199",
                "email": "jane.agent@example.com",
            },
            "principal_load_identifier": "LOAD-99",
            "freight_mode": "FTL",
            "equipment": {
                "description": "V53, 53' Van",
                "trailer_body_type": "Van",
                "trailer_length": "53 ft",
            },
            "commodity": "Poly Grind",
            "estimated_weight": 43000,
            "temperature_requirement": None,
            "rate": 1800,
            "customer_rate": None,
            "miles": None,
            "customs_broker_name": "Customs Co",
            "references": [{"kind": "po_number", "value": "PO-1"}],
            "stops": [
                {
                    "stop_type": "pickup",
                    "sequence": 1,
                    "city": "Chicago",
                    "state_or_province": "IL",
                }
            ],
        }
    )
    assert product.broker_name_snapshot == "Acme Broker LLC"
    assert product.broker_phone_snapshot == "800-555-0100"
    assert product.broker_mc_number_snapshot == "123456"
    assert product.broker_dot_number_snapshot == "654321"
    assert product.broker_contact_name_snapshot == "Jane Agent"
    assert product.broker_contact_phone_snapshot == "208-555-0199"
    assert product.broker_contact_email_snapshot == "jane.agent@example.com"
    assert product.broker_load_reference == "LOAD-99"
    assert product.mode == "FTL"
    assert product.equipment_type == "V53, 53' Van"
    assert product.trailer_type == "Van"
    assert product.trailer_size == "53 ft"
    assert product.commodity == "Poly Grind"
    assert product.estimated_weight == 43000
    assert product.temperature_requirement is None
    assert product.rate == 1800.0
    assert product.customer_rate is None
    assert product.miles is None
    assert product.customs_broker_name == "Customs Co"
    assert product.references[0].value == "PO-1"
    assert product.stops[0].city == "Chicago"


def test_translator_missing_children_map_to_none_not_invented() -> None:
    product = map_semantic_extracted_to_product(
        {
            "broker_company": {"name": "Only Name"},
            "broker_agent": {},
            "equipment": {},
        }
    )
    assert product.broker_name_snapshot == "Only Name"
    assert product.broker_phone_snapshot is None
    assert product.broker_mc_number_snapshot is None
    assert product.broker_dot_number_snapshot is None
    assert product.broker_contact_name_snapshot is None
    assert product.broker_contact_phone_snapshot is None
    assert product.broker_contact_email_snapshot is None
    assert product.broker_load_reference is None
    assert product.mode is None
    assert product.equipment_type is None
    assert product.trailer_type is None
    assert product.trailer_size is None
    assert product.rate is None
    assert product.references == []
    assert product.stops == []


def test_translator_ignores_legacy_product_keys_on_semantic_payload() -> None:
    product = map_semantic_extracted_to_product(
        {
            "broker_load_reference": "SHOULD-NOT-MAP",
            "broker_contact_phone_snapshot": "999-999-9999",
            "equipment_type": "V53-ONLY",
            "principal_load_identifier": "REAL-ID",
        }
    )
    assert product.broker_load_reference == "REAL-ID"
    assert product.broker_contact_phone_snapshot is None
    assert product.equipment_type is None


def test_generic_mailbox_mechanical_runs_after_semantic_map() -> None:
    product = map_semantic_extracted_to_product(
        {
            "broker_agent": {
                "name": "Jane Agent",
                "direct_phone": "208-555-0199",
                "email": "carriers@example.com",
            }
        }
    )
    response = LoadDocumentParseResponse(
        document={"filename": "x.pdf"},
        extracted=product,
        raw_text="Jane Agent 208-555-0199 carriers@example.com",
        warnings=[],
        field_confidence={},
        context={},
    )
    out = apply_load_parser_mechanical_validation(response)
    assert out.extracted.broker_contact_email_snapshot is None
    assert "generic_company_mailbox: broker_contact_email_snapshot" in out.warnings
    assert out.extracted.broker_contact_name_snapshot == "Jane Agent"
    assert out.extracted.broker_contact_phone_snapshot == "208-555-0199"


def test_load_reference_mechanical_normalization_runs_after_semantic_map() -> None:
    product = map_semantic_extracted_to_product(
        {"principal_load_identifier": "Load #3872125-1"}
    )
    response = LoadDocumentParseResponse(
        document={"filename": "x.pdf"},
        extracted=product,
        raw_text="Load #3872125-1",
        warnings=[],
        field_confidence={},
        context={},
    )
    out = apply_load_parser_mechanical_validation(response)
    assert out.extracted.broker_load_reference == "3872125-1"


def test_field_rules_use_semantic_paths_not_storage_names() -> None:
    blob = json.dumps(get_load_rate_con_field_rules())
    for name in (
        "broker_name_snapshot",
        "broker_phone_snapshot",
        "broker_contact_name_snapshot",
        "broker_contact_phone_snapshot",
        "broker_contact_email_snapshot",
        "broker_load_reference",
        "broker_mc_number_snapshot",
        "broker_dot_number_snapshot",
        "equipment_type",
        "trailer_type",
        "trailer_size",
    ):
        assert name not in blob
    # product_fields must be semantic paths
    rules = LOAD_RATE_CON_FIELD_RULES["rules"]
    assert rules["broker_company"]["product_fields"] == [
        "broker_company.name",
        "broker_company.main_phone",
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


def test_production_semantic_schema_and_rules_contain_no_armstrong_values() -> None:
    blob = json.dumps(_schema()) + json.dumps(LOAD_RATE_CON_FIELD_RULES)
    for needle in _ARMSTRONG_NEEDLES:
        assert needle not in blob


def test_handoff_and_schema_audit_replaces_affected_storage_names() -> None:
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion={
            "names": [],
            "mc_numbers": [],
            "usdot_numbers": [],
            "phones": [],
            "emails": [],
            "email_domains": [],
            "addresses": [],
        },
        pages=[{"page_number": 1, "text": "Rate confirmation text"}],
        filename="Armstrong.pdf",
    )
    body = build_proposed_openai_request_body_v2(handoff, model="gpt-4o-mini")
    schema = body["response_format"]["json_schema"]["schema"]
    extracted = schema["$defs"]["SemanticExtractedFields"]
    extracted_blob = json.dumps(extracted)
    rules_blob = json.dumps(handoff["field_rules"])
    user = body["messages"][1]["content"]
    for name in (
        "broker_contact_phone_snapshot",
        "broker_contact_email_snapshot",
        "broker_load_reference",
        "equipment_type",
    ):
        assert name not in extracted_blob
        assert name not in rules_blob
    assert "broker_agent.direct_phone" in rules_blob
    assert "broker_agent.email" in rules_blob
    assert "principal_load_identifier" in extracted_blob
    assert "principal_load_identifier" in rules_blob
    assert "equipment.description" in rules_blob
    assert "broker_company.main_phone" in rules_blob
    assert "ownership_precedence" in rules_blob
    assert "Entity and role ownership outrank adjacency and contact-tuple cohesion." in rules_blob
    assert "not a broker_agent" in rules_blob
    assert "carrier-owned block" in rules_blob
    assert "Entity and role ownership outrank adjacency and contact-tuple cohesion." in user
    assert "not a broker_agent" in user


def test_product_extracted_schema_still_uses_storage_names() -> None:
    """Public product contract is unchanged."""
    fields = LoadParseExtractedFields.model_fields
    assert "broker_contact_phone_snapshot" in fields
    assert "broker_load_reference" in fields
    assert "equipment_type" in fields
    assert "broker_company" not in fields
    assert "principal_load_identifier" not in fields


def test_semantic_extracted_model_requires_containers() -> None:
    parsed = SemanticExtractedFields.model_validate(
        {"broker_company": {}, "broker_agent": {}, "equipment": {}}
    )
    assert parsed.broker_agent.name is None
    assert parsed.broker_company.main_phone is None
    assert parsed.equipment.description is None
