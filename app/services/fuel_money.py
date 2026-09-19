"""Fuel/Card decimal arithmetic. Never use binary float for money or quantity."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

QUANTITY_QUANT = Decimal("0.0001")
UNIT_PRICE_QUANT = Decimal("0.000001")
DISCOUNT_RATE_QUANT = Decimal("0.000001")
MONEY_QUANT = Decimal("0.0001")

QUANTITY_PRECISION = (14, 4)
UNIT_PRICE_PRECISION = (14, 6)
DISCOUNT_RATE_PRECISION = (10, 6)
MONEY_PRECISION = (14, 4)


class FuelFloatForbidden(TypeError):
    """Raised when a financial value is supplied as IEEE float."""


def to_decimal(value: Any) -> Decimal:
    """Convert an allowed source to Decimal. Rejects float/bool."""
    if isinstance(value, bool) or isinstance(value, float):
        raise FuelFloatForbidden(
            "Fuel quantity/money/rate must use Decimal or a decimal string, never float."
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            raise ValueError("Empty numeric string is not a Fuel decimal.")
        return Decimal(text)
    raise TypeError(f"Unsupported Fuel decimal type: {type(value).__name__}")


def to_optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return to_decimal(value)


def preserve_source_numeric_string(value: Any) -> str:
    """Keep the exact supplied numeric text for provider_raw."""
    if isinstance(value, bool) or isinstance(value, float):
        raise FuelFloatForbidden("Source numeric strings must not be derived from float.")
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"Unsupported source numeric type: {type(value).__name__}")


def _quantize(value: Decimal, quant: Decimal) -> Decimal:
    return value.quantize(quant, rounding=ROUND_HALF_EVEN)


def quantize_quantity(value: Any) -> Decimal:
    return _quantize(to_decimal(value), QUANTITY_QUANT)


def quantize_unit_price(value: Any) -> Decimal:
    return _quantize(to_decimal(value), UNIT_PRICE_QUANT)


def quantize_discount_rate(value: Any) -> Decimal:
    return _quantize(to_decimal(value), DISCOUNT_RATE_QUANT)


def quantize_money(value: Any) -> Decimal:
    """Tax, discount amount, totals, fees, owner-operator charge. NUMERIC(14, 4)."""
    return _quantize(to_decimal(value), MONEY_QUANT)


def decimal_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise TypeError("decimal_json requires Decimal")
    return format(value, "f")
