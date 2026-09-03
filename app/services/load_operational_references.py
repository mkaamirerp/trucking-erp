"""Sanitize and cap the persisted load operational-references collection.

Public API field is ``references``; ORM/DB column is ``operational_references``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

MAX_LOAD_OPERATIONAL_REFERENCES = 40
MAX_KIND_LEN = 32
MAX_VALUE_LEN = 120
MAX_LABEL_LEN = 80
MAX_CONFIDENCE_LEN = 32


def sanitize_load_operational_references(raw: Any) -> list[dict[str, Any]]:
    """Drop empty/invalid items; keep kind, value, and supported optional metadata.

    Does not invent kinds or values. Caps the collection. Empty kind/value items
    are omitted rather than rejected so a mixed list can still persist.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, BaseModel):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = item
        else:
            continue
        kind = data.get("kind")
        value = data.get("value")
        if not isinstance(kind, str) or not kind.strip():
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        row: dict[str, Any] = {
            "kind": kind.strip()[:MAX_KIND_LEN],
            "value": value.strip()[:MAX_VALUE_LEN],
        }
        label = data.get("label")
        if isinstance(label, str) and label.strip():
            row["label"] = label.strip()[:MAX_LABEL_LEN]
        pc = data.get("primary_candidate")
        if isinstance(pc, bool):
            row["primary_candidate"] = pc
        confidence = data.get("confidence")
        if isinstance(confidence, str) and confidence.strip():
            row["confidence"] = confidence.strip()[:MAX_CONFIDENCE_LEN]
        out.append(row)
        if len(out) >= MAX_LOAD_OPERATIONAL_REFERENCES:
            break
    return out
