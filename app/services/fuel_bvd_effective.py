"""Effective BVD row values for review/reconciliation — corrections overlay raw source."""

from __future__ import annotations

import copy
from typing import Any

from app.services.fuel_bvd_import import BVD_SOURCE_FIELD_NAMES

# Operational fields that may be overridden by latest reviewed correction.
EFFECTIVE_BVD_FIELD_NAMES: frozenset[str] = frozenset(BVD_SOURCE_FIELD_NAMES)


def build_effective_bvd_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Return a shallow copy of the review row dict with operational columns set to
    effective values (latest reviewed correction when present, else raw source).

    Preserves field_corrections and all non-overlaid keys. Does not mutate input.
    Raw source columns remain on the original row dict returned by list_for_review.
    """
    effective = copy.copy(row)
    corrections = row.get("field_corrections") or {}
    for field_name, meta in corrections.items():
        if field_name not in EFFECTIVE_BVD_FIELD_NAMES:
            continue
        if not isinstance(meta, dict):
            continue
        reviewed = meta.get("reviewed_value")
        if reviewed is None:
            continue
        effective[field_name] = reviewed
    return effective


def build_effective_bvd_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_effective_bvd_row(r) for r in rows]
