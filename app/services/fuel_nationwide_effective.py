"""Effective Nationwide row values — correction overlay on staged/parsed source."""

from __future__ import annotations

import copy
from typing import Any

from app.services.fuel_nationwide_import import NATIONWIDE_SOURCE_FIELD_NAMES

EFFECTIVE_NATIONWIDE_FIELD_NAMES: frozenset[str] = frozenset(NATIONWIDE_SOURCE_FIELD_NAMES)


def build_effective_nationwide_row(row: dict[str, Any]) -> dict[str, Any]:
    effective = copy.copy(row)
    corrections = row.get("field_corrections") or {}
    for field_name, meta in corrections.items():
        if field_name not in EFFECTIVE_NATIONWIDE_FIELD_NAMES:
            continue
        if not isinstance(meta, dict):
            continue
        reviewed = meta.get("reviewed_value")
        if reviewed is None:
            continue
        effective[field_name] = reviewed
    return effective


def build_effective_nationwide_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_effective_nationwide_row(r) for r in rows]
