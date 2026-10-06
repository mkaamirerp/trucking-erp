"""Effective PDF review rows: latest human correction overlays raw parser values."""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.toll import TOLL_PDF_EDITABLE_FIELDS, TollPdfReviewRow


def _raw_field_value(row: TollPdfReviewRow, field_name: str) -> Any:
    return getattr(row, field_name)


def stringify_raw(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def coerce_effective_value(field_name: str, raw: Any, corrected: str | None) -> Any:
    if corrected is None:
        return raw
    text = corrected.strip()
    if field_name in {"post_date", "entry_date", "exit_date"}:
        return date.fromisoformat(text) if text else None
    if field_name == "trip_charge":
        if not text:
            raise InvalidOperation("empty trip_charge")
        return Decimal(text)
    return text or None


def build_effective_toll_pdf_row(
    row: TollPdfReviewRow,
    corrections: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return raw + effective values. Does not mutate the ORM review row."""
    overlay = corrections or {}
    effective: dict[str, Any] = {
        "row_id": int(row.id) if row.id is not None else 0,
        "source_row_order": row.source_row_order,
        "source_page_number": row.source_page_number,
        "source_group_transponder": row.source_group_transponder,
        "source_group_plate": row.source_group_plate,
        "provider_raw": dict(row.provider_raw or {}),
        "trip_charge_raw": row.trip_charge_raw,
        "corrections": {},
        "changed_fields": [],
    }
    for field_name in TOLL_PDF_EDITABLE_FIELDS:
        raw = _raw_field_value(row, field_name)
        raw_text = stringify_raw(raw)
        meta = overlay.get(field_name)
        if meta and meta.get("corrected_value") is not None:
            value = coerce_effective_value(field_name, raw, meta.get("corrected_value"))
            effective["changed_fields"].append(field_name)
            effective["corrections"][field_name] = {
                "original_value": meta.get("original_value", raw_text),
                "corrected_value": meta.get("corrected_value"),
            }
        else:
            value = raw
        if isinstance(value, Decimal):
            effective[field_name] = format(value, "f")
            effective[f"{field_name}_decimal"] = value
        elif isinstance(value, date):
            effective[field_name] = value.isoformat()
            effective[f"{field_name}_date"] = value
        else:
            effective[field_name] = value
            if field_name == "trip_charge":
                effective["trip_charge_decimal"] = Decimal(str(value))
    effective["raw"] = {name: stringify_raw(_raw_field_value(row, name)) for name in TOLL_PDF_EDITABLE_FIELDS}
    return effective


def build_effective_toll_pdf_rows(
    rows: list[TollPdfReviewRow],
    corrections_by_row: dict[int, dict[str, dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    by_row = corrections_by_row or {}
    return [
        build_effective_toll_pdf_row(row, by_row.get(int(row.id) if row.id is not None else 0))
        for row in rows
    ]


def reconcile_effective_pdf_rows(
    rows: list[dict[str, Any]],
    *,
    source_total_trip_count: int | None,
    source_total_trip_charge: Decimal | None,
) -> dict[str, Any]:
    effective_count = len(rows)
    effective_total = sum((row["trip_charge_decimal"] for row in rows), Decimal("0.00"))
    count_ok = source_total_trip_count is not None and int(source_total_trip_count) == effective_count
    total_ok = source_total_trip_charge is not None and Decimal(source_total_trip_charge) == effective_total
    return {
        "source_total_trip_count": source_total_trip_count,
        "source_total_trip_charge": format(source_total_trip_charge, "f") if source_total_trip_charge is not None else None,
        "effective_trip_count": effective_count,
        "effective_total_trip_charge": format(effective_total, "f"),
        "trip_count_matches": bool(count_ok),
        "trip_total_matches": bool(total_ok),
        "reconciliation_ok": bool(count_ok and total_ok),
    }


def copy_effective(row: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(row)
