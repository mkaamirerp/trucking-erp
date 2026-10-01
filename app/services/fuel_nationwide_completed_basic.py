"""Completed BASIC projection for processed Nationwide imports (Fuel home history)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.fuel_bvd_completed_basic import (
    distinct_purchase_card_numbers,
    format_money_display,
    money_is_nonzero,
)
from app.services.fuel_nationwide_card_total import apply_card_total_review_fields
from app.services.fuel_nationwide_import import NW_REVIEW_SOURCE_COMPLETE
from app.services.fuel_nationwide_source_reconciliation import reconcile_nationwide_source_rows

NATIONWIDE_PROVIDER = "NATIONWIDE"


def _header_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if row.get("row_type") == "HEADER":
            return row
    return None


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


def _sum_transaction_totals(rows: list[dict[str, Any]], currency: str) -> str:
    total = Decimal("0")
    cur = currency.upper()
    for row in rows:
        if row.get("row_type") != "TRANSACTION":
            continue
        if (row.get("currency") or "").upper() != cur:
            continue
        raw = row.get("total")
        if raw is None:
            continue
        text = str(raw).replace(",", "").strip()
        if not text:
            continue
        try:
            total += Decimal(text)
        except InvalidOperation:
            continue
    return format(total, "f")


def _processed_at(rows: list[dict[str, Any]], fallback: str | None = None) -> str | None:
    best = fallback
    for row in rows:
        reviewed = row.get("reviewed_at")
        if isinstance(reviewed, str) and reviewed:
            if best is None or reviewed > best:
                best = reviewed
    return best


def build_nationwide_completed_basic_projection(
    rows: list[dict[str, Any]],
    *,
    import_id: str,
    review_status: str | None = None,
    processed_at: str | None = None,
) -> dict[str, Any]:
    enriched = []
    for row in rows:
        data = dict(row)
        if data.get("row_type") == "CONTROL":
            apply_card_total_review_fields(data)
        enriched.append(data)

    header = _header_row(enriched)
    status = review_status or (str(header.get("review_status")) if header else None) or "PENDING"
    purchase_cards = distinct_purchase_card_numbers(enriched)
    units = _distinct_billed_units(enriched)
    transactions = [r for r in enriched if r.get("row_type") == "TRANSACTION"]
    controls = [r for r in enriched if r.get("row_type") == "CONTROL"]

    recon = reconcile_nationwide_source_rows(enriched)
    usd_printed = recon.usd_row_total_sum or _sum_transaction_totals(enriched, "USD")
    cad_printed = _sum_transaction_totals(enriched, "CAD")
    usd_control = recon.usd_provider_control

    return {
        "provider": NATIONWIDE_PROVIDER,
        "import_id": import_id,
        "invoice_number": (header.get("invoice_number") if header else None) or "—",
        "review_status": status,
        "read_only": status == NW_REVIEW_SOURCE_COMPLETE,
        "processed_at": _processed_at(enriched, processed_at),
        "period_start": header.get("invoice_start_date") if header else None,
        "period_end": header.get("invoice_end_date") if header else None,
        "card_number": header.get("account_code") if header else None,
        "account_code": header.get("account_code") if header else None,
        "purchase_card_count": len(purchase_cards),
        "purchase_card_numbers": purchase_cards,
        "due_date": header.get("due_date") if header else None,
        "invoice_disc_amt": "",
        "unit_count": len(units),
        "unit_numbers": units,
        "total_amount": cad_printed if money_is_nonzero(cad_printed) else usd_printed,
        "currency": "CAD" if money_is_nonzero(cad_printed) else "USD",
        "usd_transaction_total": usd_printed,
        "cad_transaction_total": cad_printed if money_is_nonzero(cad_printed) else None,
        "usd_provider_control": usd_control,
        "transaction_count": len(transactions),
        "control_count": len(controls),
        "categories": [],
        "taxes": [],
    }
