"""Approved static semantic field_rules for Load / Rate Confirmation OpenAI handoff.

Canonical source: app/contracts/TruckERP_Rate_Confirmation_AI_Handoff_Contract_v2_FULL.json
Loaded as one object. Do not rebuild rule groups in Python.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

_CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent
    / "contracts"
    / "TruckERP_Rate_Confirmation_AI_Handoff_Contract_v2_FULL.json"
)


def _load_canonical_field_rules() -> dict[str, Any]:
    payload = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    rules = payload.get("field_rules")
    if not isinstance(rules, dict):
        raise RuntimeError(f"canonical contract missing field_rules: {_CONTRACT_PATH}")
    return rules


LOAD_RATE_CON_FIELD_RULES: dict[str, Any] = _load_canonical_field_rules()

APPROVED_FIELD_RULE_KEYS: tuple[str, ...] = tuple(LOAD_RATE_CON_FIELD_RULES["rules"].keys())


def get_load_rate_con_field_rules() -> dict[str, Any]:
    """Return a deep-copy-safe static field_rules object (caller may mutate the copy)."""
    return copy.deepcopy(LOAD_RATE_CON_FIELD_RULES)
