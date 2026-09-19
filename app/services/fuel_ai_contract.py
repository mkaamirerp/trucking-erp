"""Fuel AI handoff contract loader and authority boundaries (Segment 5)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping

HANDOFF_VERSION: Final[str] = "fuel_card_statement_v1"
PROFILE: Final[str] = "fuel_card_statement"
PARSER_RULE_VERSION: Final[str] = "fuel_card_statement_v1"

CONTRACT_FILENAME: Final[str] = "TruckERP_Fuel_Card_AI_Handoff_Contract_v1.json"
CONTRACT_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "contracts" / CONTRACT_FILENAME
)

# AI may extract provider/source facts only. These fields are TruckERP-owned.
AI_FORBIDDEN_AUTHORITY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "truck_id",
        "driver_id",
        "owner_operator_payee_id",
        "classification",
        "financial_responsibility",
        "pricing_agreement_ref",
        "settlement_ref",
        "owner_operator_charge_amount",
        "oo_pricing_mode",
        "oo_pricing_rule_id",
        "oo_pricing_rule_version",
        "oo_charge_unit_price",
        "oo_benefit_per_unit",
        "oo_pricing_status",
        "oo_pricing_reason",
        "oo_pricing_inputs_json",
        "downstream_module",
        "downstream_ack_status",
        "downstream_ack_ref",
        "gate_status",
        "card_account_assignment_id",
        "historical_resolution_status",
    }
)

LAYOUT_RECOGNIZED = "RECOGNIZED"
LAYOUT_UNRECOGNIZED = "PROVIDER_LAYOUT_UNRECOGNIZED"
LAYOUT_REVIEW = "REVIEW"

ROW_ROLE_TRANSACTION = "TRANSACTION"
ROW_ROLE_CONTROL = "CONTROL"
ROW_ROLE_UNKNOWN = "UNKNOWN"

MONEY_DECIMAL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "quantity",
        "unit_price",
        "provider_discount_rate",
        "provider_discount_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "pre_tax_amount",
        "billed_amount",
        "retail_amount",
        "total_amount",
        "declared_amount",
        "discount_amount",
    }
)


@lru_cache(maxsize=1)
def load_fuel_ai_handoff_contract() -> dict[str, Any]:
    raw = CONTRACT_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise TypeError("Fuel AI handoff contract must be a JSON object")
    if data.get("handoff_version") != HANDOFF_VERSION:
        raise ValueError(
            f"Contract handoff_version mismatch: {data.get('handoff_version')!r}"
        )
    if data.get("profile") != PROFILE:
        raise ValueError(f"Contract profile mismatch: {data.get('profile')!r}")
    return data


def contract_ai_forbidden_fields(contract: Mapping[str, Any] | None = None) -> frozenset[str]:
    doc = contract or load_fuel_ai_handoff_contract()
    listed = doc.get("ai_forbidden_authority_fields") or []
    return frozenset(str(x) for x in listed) | AI_FORBIDDEN_AUTHORITY_FIELDS


def parser_rule_version_for_persistence(
    contract: Mapping[str, Any] | None = None,
) -> str:
    """Value stored on fuel_source_batches.parser_rule_version after a parse."""
    doc = contract or load_fuel_ai_handoff_contract()
    version = doc.get("parser_rule_version") or doc.get("handoff_version")
    return str(version)
