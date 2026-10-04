"""Masked / placeholder vehicle identifiers on fuel receipts."""

from __future__ import annotations

_MASKED_EXACT = frozenset({"XXXX", "XXX", "—", "-", "N/A", "NA", "TBD", "UNKNOWN"})


def is_masked_vehicle_id(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    upper = text.upper()
    if upper in _MASKED_EXACT:
        return True
    if len(text) >= 3 and set(upper) <= {"X", "*"}:
        return True
    return False
