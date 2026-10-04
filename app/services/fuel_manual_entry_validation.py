"""Manual Fuel Entry — conditional validation and deterministic derivation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.services.fuel_manual_entry_constants import (
    PROVENANCE_DERIVED,
    REQUIRED_DRAFT_FIELDS,
)
from app.services.fuel_money import (
    quantize_money,
    quantize_quantity,
    quantize_unit_price,
    to_optional_decimal,
)

MONEY_TOLERANCE = Decimal("0.0005")
# Printed fuel totals are often rounded to cents while qty × price uses more precision.
QTY_PRICE_TOTAL_TOLERANCE = Decimal("0.01")
QTY_TOLERANCE = Decimal("0.0001")


class FuelManualEntryValidationError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _dec(raw: Any) -> Decimal | None:
    return to_optional_decimal(raw)


def _money_close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= MONEY_TOLERANCE


def _qty_price_total_close(product: Decimal, total: Decimal) -> bool:
    return abs(quantize_money(product) - quantize_money(total)) <= QTY_PRICE_TOTAL_TOLERANCE


def _draft_money_str(value: Decimal) -> str:
    return format(quantize_money(value), "f")


def _draft_unit_price_str(value: Decimal) -> str:
    return format(quantize_unit_price(value).normalize(), "f")


def _normalize_draft(draft: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(draft)
    provenance = dict(out.get("field_provenance") or {})
    derived = dict(out.get("derived_fields") or {})
    review_reasons: list[str] = list(out.get("review_reasons") or [])
    requires_review = bool(out.get("requires_review"))

    for field in REQUIRED_DRAFT_FIELDS:
        val = out.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            raise FuelManualEntryValidationError(
                "REQUIRED_FIELD_MISSING",
                f"Required field missing: {field}",
                {"field": field},
            )

    unit = str(out.get("unit_number") or "").strip()
    if unit.upper() in {"XXXX", "XXX", "—", "-"}:
        requires_review = True
        if "UNIT_NUMBER_PLACEHOLDER" not in review_reasons:
            review_reasons.append("UNIT_NUMBER_PLACEHOLDER")

    qty = _dec(out.get("quantity"))
    unit_price = _dec(out.get("unit_price"))
    total = _dec(out.get("total_amount"))
    if total is None:
        raise FuelManualEntryValidationError("INVALID_TOTAL", "final amount is not a valid number")

    # 1–3: quantity / unit price / total relationships
    if qty is not None and unit_price is not None and total is not None:
        if not _qty_price_total_close(qty * unit_price, total):
            raise FuelManualEntryValidationError(
                "QTY_PRICE_TOTAL_MISMATCH",
                "quantity × unit price does not match final total",
                {
                    "quantity": str(qty),
                    "unit_price": str(unit_price),
                    "total_amount": str(total),
                },
            )
    elif qty is not None and total is not None and unit_price is None and qty != 0:
        derived_price = quantize_unit_price(total / qty)
        out["unit_price"] = _draft_unit_price_str(derived_price)
        derived["unit_price"] = PROVENANCE_DERIVED
        provenance.setdefault("unit_price", PROVENANCE_DERIVED)
        unit_price = derived_price
    elif unit_price is not None and total is not None and qty is None and unit_price != 0:
        q_unit = (out.get("quantity_unit") or "").strip().lower()
        if q_unit in {"litres", "liter", "liters", "l", "gallons", "gallon", "gal"}:
            derived_qty = quantize_quantity(total / unit_price)
            out["quantity"] = format(derived_qty, "f")
            derived["quantity"] = PROVENANCE_DERIVED
            provenance.setdefault("quantity", PROVENANCE_DERIVED)
            qty = derived_qty

    pre_tax = _dec(out.get("pre_tax_amount"))
    taxes = [
        _dec(out.get("gst_amount")),
        _dec(out.get("hst_amount")),
        _dec(out.get("pst_amount")),
        _dec(out.get("qst_amount")),
    ]
    tax_sum = sum(t for t in taxes if t is not None)
    if pre_tax is not None and tax_sum > 0 and total is not None:
        if not _money_close(quantize_money(pre_tax + tax_sum), quantize_money(total)):
            raise FuelManualEntryValidationError(
                "TAX_TOTAL_MISMATCH",
                "pre-tax + taxes does not match final total",
            )

    provider_raw = dict(out.get("provider_raw") or {})
    if provider_raw.get("unit_price_candidates"):
        winners, losers = select_reconciling_unit_price(
            qty,
            [_dec(c) for c in provider_raw["unit_price_candidates"] if _dec(c) is not None],
            total,
        )
        if winners is None:
            requires_review = True
            if "UNIT_PRICE_CANDIDATES_UNRECONCILED" not in review_reasons:
                review_reasons.append("UNIT_PRICE_CANDIDATES_UNRECONCILED")
        else:
            out["unit_price"] = format(winners, "f")
            provenance["unit_price"] = "RECEIPT_RECONCILED"
            provider_raw["unit_price_candidates_rejected"] = [
                format(x, "f") for x in (losers or []) if x is not None
            ]
            out["provider_raw"] = provider_raw

    out["field_provenance"] = provenance
    out["derived_fields"] = derived
    out["requires_review"] = requires_review
    out["review_reasons"] = review_reasons
    return out


def select_reconciling_unit_price(
    quantity: Decimal | None,
    candidates: list[Decimal],
    final_total: Decimal | None,
) -> tuple[Decimal | None, list[Decimal]]:
    if quantity is None or final_total is None or not candidates:
        return None, candidates
    winners: list[Decimal] = []
    losers: list[Decimal] = []
    for price in candidates:
        product = quantize_money(quantity * price)
        if _qty_price_total_close(product, final_total):
            winners.append(price)
        else:
            losers.append(price)
    if len(winners) == 1:
        return winners[0], losers
    return None, candidates


def validate_and_prepare_draft(draft: Mapping[str, Any], *, strict: bool = True) -> dict[str, Any]:
    """Validate required fields, apply derivations, return normalized draft + snapshot."""
    try:
        normalized = _normalize_draft(draft)
    except FuelManualEntryValidationError:
        if strict:
            raise
        normalized = dict(draft)
    snapshot = {
        "ok": True,
        "requires_review": normalized.get("requires_review", False),
        "review_reasons": normalized.get("review_reasons", []),
        "derived_fields": normalized.get("derived_fields", {}),
    }
    normalized["validation_snapshot"] = snapshot
    return normalized
