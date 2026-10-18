"""Load commercial rate / customer_rate — Decimal cents-safe parsing (Issue I8)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

LOAD_COMMERCIAL_MONEY_QUANT = Decimal("0.01")
# loads.rate NUMERIC(12, 2); loads.customer_rate NUMERIC(14, 2)
_LOAD_RATE_MAX = Decimal("9999999999.99")
_CUSTOMER_RATE_MAX = Decimal("999999999999.99")


def parse_optional_load_commercial_money(
    value: Any,
    *,
    field: str = "money",
    max_magnitude: Decimal | None = None,
) -> Decimal | None:
    """Parse API, parser, or draft JSON money into a two-decimal non-negative Decimal."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a monetary amount")
    if isinstance(value, Decimal):
        amount = value
        if not amount.is_finite():
            raise ValueError(f"{field} must be a finite monetary amount")
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        if not (value == value and abs(value) != float("inf")):  # NaN / inf
            raise ValueError(f"{field} must be a finite monetary amount")
        amount = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip().replace(",", "").replace("$", "")
        if not text:
            return None
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"{field} must be a monetary amount") from exc
    else:
        raise ValueError(f"{field} must be a monetary amount")

    if not amount.is_finite():
        raise ValueError(f"{field} must be a finite monetary amount")

    if amount < 0:
        raise ValueError(f"{field} must be >= 0")

    try:
        quantized = amount.quantize(LOAD_COMMERCIAL_MONEY_QUANT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a monetary amount") from exc
    cap = max_magnitude if max_magnitude is not None else _CUSTOMER_RATE_MAX
    if quantized.copy_abs() > cap:
        raise ValueError(f"{field} exceeds allowed magnitude")
    return quantized


def parse_load_rate(value: Any) -> Decimal | None:
    return parse_optional_load_commercial_money(value, field="rate", max_magnitude=_LOAD_RATE_MAX)


def parse_load_customer_rate(value: Any) -> Decimal | None:
    return parse_optional_load_commercial_money(
        value, field="customer_rate", max_magnitude=_CUSTOMER_RATE_MAX
    )
