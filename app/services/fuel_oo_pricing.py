"""Segment 4 owner-operator fuel pricing.

Provider financial truth and O/O settlement charge are separate. Never overwrite
provider retail/discount/billed/tax/total/currency. Decimal only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Final, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.fuel_historical_resolution import (
    FuelHistoryOverlapError,
    find_overlapping_history_rows,
    intervals_overlap,
)
from app.services.fuel_money import quantize_money, quantize_unit_price, to_decimal, to_optional_decimal

MODE_NO_DISCOUNT = "NO_DISCOUNT"
MODE_FULL_PROVIDER_DISCOUNT = "FULL_PROVIDER_DISCOUNT"
MODE_FIXED_DISCOUNT = "FIXED_DISCOUNT"
MODE_PERCENT_OF_PROVIDER_DISCOUNT = "PERCENT_OF_PROVIDER_DISCOUNT"

PRICING_MODES: Final[frozenset[str]] = frozenset(
    {
        MODE_NO_DISCOUNT,
        MODE_FULL_PROVIDER_DISCOUNT,
        MODE_FIXED_DISCOUNT,
        MODE_PERCENT_OF_PROVIDER_DISCOUNT,
    }
)

STATUS_CALCULATED = "CALCULATED"
STATUS_NOT_APPLICABLE_COMPANY_DRIVER = "NOT_APPLICABLE_COMPANY_DRIVER"
STATUS_REVIEW_MISSING_RULE = "REVIEW_MISSING_RULE"
STATUS_REVIEW_MULTIPLE_RULES = "REVIEW_MULTIPLE_RULES"
STATUS_REVIEW_MISSING_INPUT = "REVIEW_MISSING_INPUT"
STATUS_REVIEW_INVALID_RULE = "REVIEW_INVALID_RULE"
STATUS_REVIEW_MISSING_POINT_IN_TIME = "REVIEW_MISSING_POINT_IN_TIME"
STATUS_REVIEW_AMBIGUOUS_DATE_ONLY = "REVIEW_AMBIGUOUS_DATE_ONLY"

# Ownership / responsibility signals that must not create an O/O fuel charge.
_COMPANY_OWNERSHIP = frozenset({"company", "company_owned", "COMPANY", "COMPANY_OWNED"})
_COMPANY_RESPONSIBILITY = frozenset(
    {
        "company",
        "company_expense",
        "company_driver",
        "COMPANY",
        "COMPANY_EXPENSE",
        "COMPANY_DRIVER",
    }
)


@dataclass(frozen=True)
class OoFuelPricingResult:
    status: str
    pricing_mode: str | None = None
    pricing_rule_id: int | None = None
    pricing_rule_version: str | None = None
    pump_unit_price: Decimal | None = None
    provider_discount_per_unit: Decimal | None = None
    provider_cost_per_unit: Decimal | None = None
    oo_benefit_per_unit: Decimal | None = None
    oo_charge_unit_price: Decimal | None = None
    quantity: Decimal | None = None
    owner_operator_charge_amount: Decimal | None = None
    reason: str | None = None
    inputs: dict[str, Any] | None = None

    @property
    def requires_review(self) -> bool:
        return self.status.startswith("REVIEW_")

    @property
    def provider_fields_unchanged(self) -> bool:
        """Calculator never mutates provider source amounts."""
        return True


def pricing_point_in_time(
    *,
    transaction_datetime: datetime | None,
) -> datetime | None:
    """Aware provider timestamp only. Never invents UTC midnight from a date."""
    if transaction_datetime is None:
        return None
    if transaction_datetime.tzinfo is None:
        raise ValueError("transaction_datetime must be timezone-aware for pricing resolution")
    return transaction_datetime


def source_date_local_interval(
    source_date: date,
    *,
    provider_timezone: str | None,
) -> tuple[datetime, datetime] | None:
    """Half-open [local midnight, next local midnight) in a real provider zone.

    Returns None when timezone is missing/invalid — callers must REVIEW, never
    fall back to UTC.
    """
    if provider_timezone is None:
        return None
    name = str(provider_timezone).strip()
    if not name:
        return None
    try:
        tz = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return None
    day_start = datetime.combine(source_date, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def _interval_covers(row: Mapping[str, Any], at: datetime) -> bool:
    start = row["effective_from"]
    if start.tzinfo is None:
        raise ValueError("pricing rule effective_from must be timezone-aware")
    if at < start:
        return False
    end = row.get("effective_to")
    if end is None:
        return True
    if end.tzinfo is None:
        raise ValueError("pricing rule effective_to must be timezone-aware")
    return at < end


def _rule_covers_full_interval(
    rule: Mapping[str, Any],
    interval_start: datetime,
    interval_end: datetime,
) -> bool:
    """True when every instant in [interval_start, interval_end) is covered by rule."""
    if not _interval_covers(rule, interval_start):
        return False
    end = rule.get("effective_to")
    if end is None:
        return True
    if end.tzinfo is None:
        raise ValueError("pricing rule effective_to must be timezone-aware")
    return end >= interval_end


def is_company_driver_charge_forbidden(
    *,
    ownership_type: str | None = None,
    financial_responsibility: str | None = None,
    is_company_driver: bool | None = None,
) -> bool:
    if is_company_driver is True:
        return True
    if ownership_type is not None and str(ownership_type).strip() in _COMPANY_OWNERSHIP:
        # Company-owned truck with company-driver responsibility (or unspecified driver charge).
        if financial_responsibility is None:
            return True
        if str(financial_responsibility).strip() in _COMPANY_RESPONSIBILITY:
            return True
    if financial_responsibility is not None and str(financial_responsibility).strip() in {
        "company_driver",
        "COMPANY_DRIVER",
    }:
        return True
    return False


def assert_oo_pricing_rules_have_no_overlap(rules: Sequence[Mapping[str, Any]]) -> None:
    """One applicable pricing rule per payee at a time. No silent merge."""
    overlaps = find_overlapping_history_rows(
        rules, key_fn=lambda r: (int(r["owner_operator_payee_id"]),)
    )
    if overlaps:
        raise FuelHistoryOverlapError(
            "Overlapping fuel_oo_pricing_rules for the same owner_operator_payee_id"
        )


def assert_proposed_oo_pricing_rule_no_overlap(
    *,
    proposed: Mapping[str, Any],
    existing_rules: Sequence[Mapping[str, Any]],
) -> None:
    combined = [dict(r) for r in existing_rules] + [dict(proposed)]
    assert_oo_pricing_rules_have_no_overlap(combined)


def resolve_oo_pricing_rule(
    *,
    owner_operator_payee_id: int | None,
    at: datetime | None,
    rules: Sequence[Mapping[str, Any]],
) -> tuple[str, Mapping[str, Any] | None]:
    """Point-in-time resolution for an aware provider timestamp."""
    if owner_operator_payee_id is None:
        return STATUS_REVIEW_MISSING_INPUT, None
    if at is None:
        return STATUS_REVIEW_MISSING_POINT_IN_TIME, None
    covering = [
        r
        for r in rules
        if int(r["owner_operator_payee_id"]) == int(owner_operator_payee_id)
        and _interval_covers(r, at)
    ]
    if len(covering) == 0:
        return STATUS_REVIEW_MISSING_RULE, None
    if len(covering) > 1:
        return STATUS_REVIEW_MULTIPLE_RULES, None
    return STATUS_CALCULATED, covering[0]


def resolve_oo_pricing_rule_for_source_date(
    *,
    owner_operator_payee_id: int | None,
    source_date: date | None,
    provider_timezone: str | None,
    rules: Sequence[Mapping[str, Any]],
) -> tuple[str, Mapping[str, Any] | None]:
    """DATE_ONLY resolution: one rule must cover the entire local calendar day.

    Never converts the source date to UTC midnight. Without a legitimate
    provider timezone, returns REVIEW. If a rule boundary falls inside the
    local day (or coverage is partial/multiple), returns REVIEW.
    """
    if owner_operator_payee_id is None:
        return STATUS_REVIEW_MISSING_INPUT, None
    if source_date is None:
        return STATUS_REVIEW_MISSING_POINT_IN_TIME, None
    interval = source_date_local_interval(source_date, provider_timezone=provider_timezone)
    if interval is None:
        return STATUS_REVIEW_AMBIGUOUS_DATE_ONLY, None
    day_start, day_end = interval
    payee_rules = [
        r for r in rules if int(r["owner_operator_payee_id"]) == int(owner_operator_payee_id)
    ]
    overlapping = [
        r
        for r in payee_rules
        if intervals_overlap(
            r["effective_from"],
            r.get("effective_to"),
            day_start,
            day_end,
        )
    ]
    if len(overlapping) == 0:
        return STATUS_REVIEW_MISSING_RULE, None
    if len(overlapping) > 1:
        return STATUS_REVIEW_AMBIGUOUS_DATE_ONLY, None
    rule = overlapping[0]
    if not _rule_covers_full_interval(rule, day_start, day_end):
        return STATUS_REVIEW_AMBIGUOUS_DATE_ONLY, None
    return STATUS_CALCULATED, rule


def _need_provider_discount(mode: str) -> bool:
    return mode in {MODE_FULL_PROVIDER_DISCOUNT, MODE_PERCENT_OF_PROVIDER_DISCOUNT}


def calculate_oo_fuel_charge(
    *,
    pricing_mode: str,
    pump_unit_price: Any,
    quantity: Any,
    provider_discount_per_unit: Any = None,
    fixed_discount_per_unit: Any = None,
    percent_of_provider_discount: Any = None,
    pricing_rule_id: int | None = None,
    pricing_rule_version: str | None = None,
) -> OoFuelPricingResult:
    """Compute O/O charge from pump/discount inputs. Never invents provider discount."""
    mode = (pricing_mode or "").strip().upper()
    inputs = {
        "pricing_mode": mode,
        "pump_unit_price": None if pump_unit_price is None else str(pump_unit_price),
        "provider_discount_per_unit": (
            None if provider_discount_per_unit is None else str(provider_discount_per_unit)
        ),
        "fixed_discount_per_unit": (
            None if fixed_discount_per_unit is None else str(fixed_discount_per_unit)
        ),
        "percent_of_provider_discount": (
            None if percent_of_provider_discount is None else str(percent_of_provider_discount)
        ),
        "quantity": None if quantity is None else str(quantity),
    }
    if mode not in PRICING_MODES:
        return OoFuelPricingResult(
            status=STATUS_REVIEW_INVALID_RULE,
            pricing_mode=mode or None,
            pricing_rule_id=pricing_rule_id,
            pricing_rule_version=pricing_rule_version,
            reason="UNKNOWN_PRICING_MODE",
            inputs=inputs,
        )
    if pump_unit_price is None or quantity is None:
        return OoFuelPricingResult(
            status=STATUS_REVIEW_MISSING_INPUT,
            pricing_mode=mode,
            pricing_rule_id=pricing_rule_id,
            pricing_rule_version=pricing_rule_version,
            reason="MISSING_PUMP_PRICE_OR_QUANTITY",
            inputs=inputs,
        )

    pump = quantize_unit_price(pump_unit_price)
    qty = to_decimal(quantity)
    prov_disc = to_optional_decimal(provider_discount_per_unit)
    if prov_disc is not None:
        prov_disc = quantize_unit_price(prov_disc)
    provider_cost = None if prov_disc is None else quantize_unit_price(pump - prov_disc)

    if _need_provider_discount(mode) and prov_disc is None:
        return OoFuelPricingResult(
            status=STATUS_REVIEW_MISSING_INPUT,
            pricing_mode=mode,
            pricing_rule_id=pricing_rule_id,
            pricing_rule_version=pricing_rule_version,
            pump_unit_price=pump,
            provider_discount_per_unit=None,
            provider_cost_per_unit=None,
            quantity=qty,
            reason="MISSING_PROVIDER_DISCOUNT",
            inputs=inputs,
        )

    if mode == MODE_NO_DISCOUNT:
        benefit = quantize_unit_price(Decimal("0"))
        charge_price = pump
    elif mode == MODE_FULL_PROVIDER_DISCOUNT:
        assert prov_disc is not None
        benefit = prov_disc
        charge_price = quantize_unit_price(pump - benefit)
    elif mode == MODE_FIXED_DISCOUNT:
        if fixed_discount_per_unit is None:
            return OoFuelPricingResult(
                status=STATUS_REVIEW_MISSING_INPUT,
                pricing_mode=mode,
                pricing_rule_id=pricing_rule_id,
                pricing_rule_version=pricing_rule_version,
                pump_unit_price=pump,
                provider_discount_per_unit=prov_disc,
                provider_cost_per_unit=provider_cost,
                quantity=qty,
                reason="MISSING_FIXED_DISCOUNT",
                inputs=inputs,
            )
        benefit = quantize_unit_price(fixed_discount_per_unit)
        charge_price = quantize_unit_price(pump - benefit)
    else:  # PERCENT_OF_PROVIDER_DISCOUNT
        assert prov_disc is not None
        if percent_of_provider_discount is None:
            return OoFuelPricingResult(
                status=STATUS_REVIEW_MISSING_INPUT,
                pricing_mode=mode,
                pricing_rule_id=pricing_rule_id,
                pricing_rule_version=pricing_rule_version,
                pump_unit_price=pump,
                provider_discount_per_unit=prov_disc,
                provider_cost_per_unit=provider_cost,
                quantity=qty,
                reason="MISSING_PERCENT_OF_PROVIDER_DISCOUNT",
                inputs=inputs,
            )
        share = to_decimal(percent_of_provider_discount)
        if share < 0 or share > 1:
            return OoFuelPricingResult(
                status=STATUS_REVIEW_INVALID_RULE,
                pricing_mode=mode,
                pricing_rule_id=pricing_rule_id,
                pricing_rule_version=pricing_rule_version,
                pump_unit_price=pump,
                provider_discount_per_unit=prov_disc,
                provider_cost_per_unit=provider_cost,
                quantity=qty,
                reason="PERCENT_OUT_OF_RANGE",
                inputs=inputs,
            )
        benefit = quantize_unit_price(prov_disc * share)
        charge_price = quantize_unit_price(pump - benefit)

    charge_amount = quantize_money(charge_price * qty)
    return OoFuelPricingResult(
        status=STATUS_CALCULATED,
        pricing_mode=mode,
        pricing_rule_id=pricing_rule_id,
        pricing_rule_version=pricing_rule_version,
        pump_unit_price=pump,
        provider_discount_per_unit=prov_disc,
        provider_cost_per_unit=provider_cost,
        oo_benefit_per_unit=benefit,
        oo_charge_unit_price=charge_price,
        quantity=qty,
        owner_operator_charge_amount=charge_amount,
        reason=None,
        inputs=inputs,
    )


def price_fuel_transaction_for_oo(
    *,
    owner_operator_payee_id: int | None,
    ownership_type: str | None,
    financial_responsibility: str | None,
    is_company_driver: bool | None,
    transaction_datetime: datetime | None,
    transaction_date: date | None,
    pump_unit_price: Any,
    quantity: Any,
    provider_discount_per_unit: Any,
    rules: Sequence[Mapping[str, Any]],
    provider_timezone: str | None = None,
) -> OoFuelPricingResult:
    """Resolve effective rule + calculate. Does not mutate provider source fields.

    Aware ``transaction_datetime`` uses point-in-time resolution. DATE_ONLY
    (``transaction_date`` without datetime) requires ``provider_timezone`` and
    unambiguous full-day coverage; never invents UTC midnight.
    """
    if is_company_driver_charge_forbidden(
        ownership_type=ownership_type,
        financial_responsibility=financial_responsibility,
        is_company_driver=is_company_driver,
    ):
        return OoFuelPricingResult(
            status=STATUS_NOT_APPLICABLE_COMPANY_DRIVER,
            owner_operator_charge_amount=None,
            reason="COMPANY_DRIVER_NO_OO_CHARGE",
            inputs={
                "ownership_type": ownership_type,
                "financial_responsibility": financial_responsibility,
                "is_company_driver": is_company_driver,
            },
        )

    if transaction_datetime is not None:
        at = pricing_point_in_time(transaction_datetime=transaction_datetime)
        status, rule = resolve_oo_pricing_rule(
            owner_operator_payee_id=owner_operator_payee_id,
            at=at,
            rules=rules,
        )
        resolution_inputs: dict[str, Any] = {
            "owner_operator_payee_id": owner_operator_payee_id,
            "resolution": "point_in_time",
            "at": at.isoformat() if at else None,
        }
    elif transaction_date is not None:
        status, rule = resolve_oo_pricing_rule_for_source_date(
            owner_operator_payee_id=owner_operator_payee_id,
            source_date=transaction_date,
            provider_timezone=provider_timezone,
            rules=rules,
        )
        interval = source_date_local_interval(
            transaction_date, provider_timezone=provider_timezone
        )
        resolution_inputs = {
            "owner_operator_payee_id": owner_operator_payee_id,
            "resolution": "source_date_interval",
            "source_date": transaction_date.isoformat(),
            "provider_timezone": provider_timezone,
            "interval_start": interval[0].isoformat() if interval else None,
            "interval_end": interval[1].isoformat() if interval else None,
        }
    else:
        status, rule = STATUS_REVIEW_MISSING_POINT_IN_TIME, None
        resolution_inputs = {
            "owner_operator_payee_id": owner_operator_payee_id,
            "resolution": "missing",
        }

    if status != STATUS_CALCULATED or rule is None:
        return OoFuelPricingResult(
            status=status if status != STATUS_CALCULATED else STATUS_REVIEW_MISSING_RULE,
            reason=status,
            inputs=resolution_inputs,
        )

    return calculate_oo_fuel_charge(
        pricing_mode=str(rule["pricing_mode"]),
        pump_unit_price=pump_unit_price,
        quantity=quantity,
        provider_discount_per_unit=provider_discount_per_unit,
        fixed_discount_per_unit=rule.get("fixed_discount_per_unit"),
        percent_of_provider_discount=rule.get("percent_of_provider_discount"),
        pricing_rule_id=None if rule.get("id") is None else int(rule["id"]),
        pricing_rule_version=None if rule.get("rule_version") is None else str(rule["rule_version"]),
    )


# Provider source columns that O/O pricing must never write.
PROVIDER_IMMUTABLE_AMOUNT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "unit_price",
        "provider_discount_rate",
        "provider_discount_amount",
        "billed_amount",
        "retail_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "pre_tax_amount",
        "total_amount",
        "currency",
        "currency_raw",
        "missed_discount_amount",
        "out_of_network_fee",
    }
)


def oo_pricing_result_as_derived_fields(result: OoFuelPricingResult) -> dict[str, Any]:
    """Map calculator output onto FuelTransaction derived columns only.

    Never includes provider amount/currency fields.
    """
    fields = {
        "owner_operator_charge_amount": result.owner_operator_charge_amount,
        "oo_pricing_mode": result.pricing_mode,
        "oo_pricing_rule_id": result.pricing_rule_id,
        "oo_pricing_rule_version": result.pricing_rule_version,
        "oo_charge_unit_price": result.oo_charge_unit_price,
        "oo_benefit_per_unit": result.oo_benefit_per_unit,
        "oo_pricing_status": result.status,
        "oo_pricing_reason": result.reason,
        "oo_pricing_inputs_json": result.inputs,
    }
    assert PROVIDER_IMMUTABLE_AMOUNT_FIELDS.isdisjoint(fields.keys())
    return fields
