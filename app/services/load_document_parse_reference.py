"""Product-owned reference extraction and ranking for guarded load parsing."""

from __future__ import annotations

import re

from typing import Any

_REFERENCE_PRIORITY = {
    "load_number": 100,
    "order_number": 95,
    "confirmation_number": 90,
    "reference_number": 85,
    "shipment_number": 75,
    "po_number": 65,
    "bol_number": 55,
    "pro_number": 45,
    "fb_number": 40,
    "el_number": 40,
}
_SUSPICIOUS_REFERENCE_VALUES = {
    "information",
    "information sheet",
    "load",
    "sheet",
    "type",
    "size",
    "date",
    "time",
    "throughout",
    "app",
}


def rank_reference_candidates(diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    candidates = []
    if isinstance(diagnostics, dict) and isinstance(diagnostics.get("reference_candidates"), list):
        candidates = [c for c in diagnostics["reference_candidates"] if isinstance(c, dict)]

    usable = [c for c in candidates if not _is_suspicious_reference(str(c.get("value") or ""))]
    ranked = sorted(
        usable,
        key=lambda c: (
            -_REFERENCE_PRIORITY.get(str(c.get("kind") or ""), 10),
            int(c.get("line") or 999_999),
            str(c.get("value") or ""),
        ),
    )
    primary = ranked[0] if ranked else None
    return {
        "primary": primary,
        "ranked": ranked[:20],
    }


def merge_ranked_references_into_extracted(
    extracted: dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    field_confidence: dict[str, str] = {}
    ranking = rank_reference_candidates(diagnostics)
    primary = ranking.get("primary") if isinstance(ranking.get("primary"), dict) else None

    existing_refs = out.get("references") if isinstance(out.get("references"), list) else []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in existing_refs:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        value = str(item.get("value") or "").strip()
        if kind and value:
            by_key[(kind, value.casefold())] = dict(item)

    for candidate in ranking.get("ranked") or []:
        if not isinstance(candidate, dict):
            continue
        kind = str(candidate.get("kind") or "").strip()
        value = str(candidate.get("value") or "").strip()
        if not kind or not value:
            continue
        by_key.setdefault(
            (kind, value.casefold()),
            {
                "kind": kind,
                "value": value,
                "label": kind,
                "primary_candidate": bool(primary and primary.get("kind") == kind and primary.get("value") == value),
                "confidence": "medium",
            },
        )

    out["references"] = list(by_key.values())

    current_ref = str(out.get("broker_load_reference") or "").strip()
    if primary and (not current_ref or _is_suspicious_reference(current_ref)):
        out["broker_load_reference"] = str(primary.get("value") or "").strip() or None
        if out.get("broker_load_reference"):
            action = "replaced" if current_ref else "filled"
            warnings.append(f"[guarded] broker_load_reference {action} from ranked document reference candidate.")
            field_confidence["broker_load_reference"] = "medium"

    if isinstance(diagnostics, dict):
        diagnostics["reference_ranking"] = ranking

    return out, warnings, field_confidence


def _is_suspicious_reference(value: str) -> bool:
    v = value.strip().casefold()
    if v in _SUSPICIOUS_REFERENCE_VALUES:
        return True
    # Table-parse noise often captures weights/rates as "reference" (e.g. 42180.00 under Reference #).
    raw = value.strip().replace(",", "")
    if raw and re.fullmatch(r"\d+\.\d{2}", raw):
        return True
    return not any(ch.isdigit() for ch in v) and len(v) < 16
