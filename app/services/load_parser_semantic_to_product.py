"""Deterministic map from OpenAI semantic extraction onto product parse fields.

Mechanical validation continues to operate on LoadParseExtractedFields names.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.schemas.load_document_parse import (
    LoadParseExtractedFields,
    LoadParseReferenceItem,
    LoadParseStopItem,
)
from app.schemas.load_document_parse_semantic import (
    SemanticExtractedFields,
    coerce_semantic_extracted,
)


def map_semantic_extracted_to_product(
    extracted: SemanticExtractedFields | dict[str, Any] | None,
) -> LoadParseExtractedFields:
    """Map AI semantic fields onto existing LoadParseExtractedFields. Never invent values."""
    semantic = (
        extracted
        if isinstance(extracted, SemanticExtractedFields)
        else coerce_semantic_extracted(extracted)
    )
    company = semantic.broker_company
    agent = semantic.broker_agent
    equipment = semantic.equipment
    return LoadParseExtractedFields(
        broker_name_snapshot=_opt_str(company.name),
        broker_phone_snapshot=_opt_str(company.main_phone),
        broker_mc_number_snapshot=_opt_str(company.mc_number),
        broker_dot_number_snapshot=_opt_str(company.dot_number),
        broker_contact_name_snapshot=_opt_str(agent.name),
        broker_contact_phone_snapshot=_opt_str(agent.direct_phone),
        broker_contact_email_snapshot=_opt_str(agent.email),
        broker_load_reference=_opt_str(semantic.principal_load_identifier),
        mode=_opt_str(semantic.freight_mode),
        equipment_type=_opt_str(equipment.description),
        trailer_type=_opt_str(equipment.trailer_body_type),
        trailer_size=_opt_str(equipment.trailer_length),
        commodity=_opt_str(semantic.commodity),
        estimated_weight=_opt_int(semantic.estimated_weight),
        temperature_requirement=_opt_str(semantic.temperature_requirement),
        rate=_opt_float(semantic.rate),
        customer_rate=_opt_float(semantic.customer_rate),
        miles=_opt_float(semantic.miles),
        customs_broker_name=_opt_str(semantic.customs_broker_name),
        references=_map_references(semantic.references),
        stops=_map_stops(semantic.stops),
    )


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _opt_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    return None


def _map_references(items: Any) -> list[LoadParseReferenceItem]:
    if not isinstance(items, list):
        return []
    out: list[LoadParseReferenceItem] = []
    for item in items:
        if isinstance(item, LoadParseReferenceItem):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        try:
            out.append(LoadParseReferenceItem.model_validate(item))
        except ValidationError:
            continue
    return out


def _map_stops(items: Any) -> list[LoadParseStopItem]:
    if not isinstance(items, list):
        return []
    out: list[LoadParseStopItem] = []
    for item in items:
        if isinstance(item, LoadParseStopItem):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        try:
            out.append(LoadParseStopItem.model_validate(item))
        except ValidationError:
            continue
    return out
