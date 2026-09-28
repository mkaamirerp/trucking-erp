"""Completed BASIC projection for processed BVD imports (operational history view)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

BVD_PROVIDER = "BVD"
BVD_REVIEW_COMPLETE = "SOURCE_REVIEWED"

TAX_FIELDS: tuple[tuple[str, str], ...] = (
    ("hst", "HST"),
    ("gst", "GST"),
    ("pst", "PST"),
    ("qst", "QST"),
)

CATEGORY_LABEL_OVERRIDES: dict[str, str] = {
    "TA": "Fuel / TA",
    "DF": "DEF",
    "TF": "Trailer",
    "Manual": "Manual",
    "Express": "Express",
    "Scale": "Scale",
    "Cash Advance": "Cash Advance",
    "Additive": "Additive",
    "Oil": "Oil",
    "Lubricant": "Lubricant",
}


def _parse_money(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def money_is_nonzero(raw: Any) -> bool:
    dec = _parse_money(raw)
    return dec is not None and dec != 0


def format_money_display(raw: Any) -> str:
    dec = _parse_money(raw)
    if dec is None:
        return ""
    return f"{dec:,.2f}"


def _row_get(row: dict[str, Any], field: str) -> Any:
    return row.get(field)


def _category_label(row: dict[str, Any]) -> str:
    label = (_row_get(row, "row_label") or _row_get(row, "product") or "").strip()
    if not label:
        return "Category"
    return CATEGORY_LABEL_OVERRIDES.get(label, label)


def _category_amount(row: dict[str, Any]) -> str:
    return format_money_display(_row_get(row, "final_amount") or _row_get(row, "final_amt"))


def _distinct_billed_units(rows: list[dict[str, Any]]) -> list[str]:
    units: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("row_type") != "TRANSACTION":
            continue
        unit = str(row.get("unit_number") or "").strip()
        if not unit or unit in seen:
            continue
        seen.add(unit)
        units.append(unit)
    return units


def _header_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if row.get("row_type") == "HEADER":
            return row
    return None


def _grand_total_statement_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if row.get("row_type") != "GRAND_TOTAL":
            continue
        if str(row.get("row_label") or "").strip() == "Grand Total":
            return row
    return None


def _nonzero_tax_lines(source_row: dict[str, Any] | None) -> list[dict[str, str]]:
    if not source_row:
        return []
    lines: list[dict[str, str]] = []
    for field, label in TAX_FIELDS:
        raw = _row_get(source_row, field)
        if money_is_nonzero(raw):
            lines.append({"key": field, "label": label, "amount": format_money_display(raw)})
    return lines


def _nonzero_category_lines(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for row in rows:
        if row.get("row_type") != "GRAND_TOTAL":
            continue
        if str(row.get("row_label") or "").strip() == "Grand Total":
            continue
        amount_raw = _row_get(row, "final_amount") or _row_get(row, "final_amt")
        if not money_is_nonzero(amount_raw):
            continue
        key = str(_row_get(row, "product") or _row_get(row, "row_label") or "category").strip()
        lines.append(
            {
                "key": key,
                "label": _category_label(row),
                "amount": _category_amount(row),
            }
        )
    return lines


def _processed_at(rows: list[dict[str, Any]]) -> str | None:
    best: str | None = None
    for row in rows:
        reviewed = row.get("reviewed_at")
        if isinstance(reviewed, str) and reviewed:
            if best is None or reviewed > best:
                best = reviewed
    return best


def build_bvd_completed_basic_projection(
    rows: list[dict[str, Any]],
    *,
    import_id: str,
    review_status: str | None = None,
) -> dict[str, Any]:
    """Single-import operational summary; omits zero-value tax/category noise."""
    header = _header_row(rows)
    status = review_status or (str(header.get("review_status")) if header else None) or "PENDING"
    grand = _grand_total_statement_row(rows)
    units = _distinct_billed_units(rows)

    total_raw = None
    currency = None
    disc_raw = None
    if grand is not None:
        total_raw = _row_get(grand, "final_amount") or _row_get(grand, "final_amt")
        currency = _row_get(grand, "cur")
        disc_raw = _row_get(grand, "disc_amt")
    if header and not currency:
        currency = _row_get(header, "cur")

    return {
        "provider": BVD_PROVIDER,
        "import_id": import_id,
        "invoice_number": (header.get("invoice_number") if header else None) or "—",
        "review_status": status,
        "read_only": status == BVD_REVIEW_COMPLETE,
        "processed_at": _processed_at(rows),
        "period_start": header.get("start_date") if header else None,
        "period_end": header.get("end_date") if header else None,
        "card_number": header.get("card_number") if header else None,
        "due_date": header.get("due_date") if header else None,
        "invoice_disc_amt": format_money_display(disc_raw) if disc_raw is not None else "",
        "unit_count": len(units),
        "unit_numbers": units,
        "total_amount": format_money_display(total_raw) if money_is_nonzero(total_raw) else format_money_display(total_raw),
        "currency": currency,
        "categories": _nonzero_category_lines(rows),
        "taxes": _nonzero_tax_lines(grand),
    }
