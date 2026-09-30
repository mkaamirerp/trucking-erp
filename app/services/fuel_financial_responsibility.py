"""Fuel-owned financial responsibility and O/O charge basis (no Payroll/Settlement)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from app.services.fuel_charge_categories import (
    CATEGORY_CASH_ADVANCE,
    CATEGORY_DEF,
    CATEGORY_FUEL,
    CATEGORY_LUMPER,
    CATEGORY_OTHER,
    CATEGORY_PARKING,
    CATEGORY_PRODUCT_PURCHASE,
    CATEGORY_REPAIR_OR_SERVICE,
    CATEGORY_SCALE,
    CATEGORY_TOLL,
    CATEGORY_UNMAPPED,
)
from app.services.fuel_historical_resolution import (
    STATUS_RESOLVED,
    HistoricalResolution,
    resolve_ownership_at,
)
from app.services.fuel_money import quantize_unit_price
from app.services.fuel_oo_pricing import (
    OoFuelPricingResult,
    calculate_oo_fuel_charge,
    price_fuel_transaction_for_oo,
)

# Canonical responsibility outcomes (Fuel module).
RESPONSIBILITY_COMPANY_EXPENSE = "COMPANY_EXPENSE"
RESPONSIBILITY_DRIVER_DEDUCTION = "DRIVER_DEDUCTION"
RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION = "OWNER_OPERATOR_DEDUCTION"
RESPONSIBILITY_REVIEW_REQUIRED = "REVIEW_REQUIRED"

_OWNERSHIP_COMPANY = frozenset({"company", "company_owned", "COMPANY", "COMPANY_OWNED"})
_OWNERSHIP_OO = frozenset(
    {"owner_operator", "owner-operator", "OWNER_OPERATOR", "owner_operator_leased_on"}
)

# Settlement tax allocation on O/O charges is NOT LOCKED in repo contracts.
TAX_TREATMENT_FOR_SETTLEMENT = "NOT_LOCKED"


@dataclass(frozen=True)
class FuelFinancialResponsibilityResult:
    """Pure decision output; safe to persist on FuelTransaction derived columns."""

    financial_responsibility: str
    settlement_deduction_candidate: bool
    responsible_payee_id: int | None
    reason: str
    category: str
    ownership_type: str | None = None
    driver_id_snapshot: int | None = None
    oo_pricing: OoFuelPricingResult | None = None
    company_retained_discount_per_unit: Decimal | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_review(self) -> bool:
        return self.financial_responsibility == RESPONSIBILITY_REVIEW_REQUIRED


def _norm_category(category: str | None) -> str:
    return (category or CATEGORY_UNMAPPED).strip().upper() or CATEGORY_UNMAPPED


def _is_company_ownership(ownership_type: str | None) -> bool:
    if ownership_type is None:
        return False
    return str(ownership_type).strip() in _OWNERSHIP_COMPANY


def _is_oo_ownership(ownership_type: str | None) -> bool:
    if ownership_type is None:
        return False
    return str(ownership_type).strip() in _OWNERSHIP_OO


def company_retained_provider_discount_per_unit(
    *,
    provider_discount_per_unit: Decimal | None,
    oo_benefit_per_unit: Decimal | None,
) -> Decimal | None:
    if provider_discount_per_unit is None or oo_benefit_per_unit is None:
        return None
    return quantize_unit_price(provider_discount_per_unit - oo_benefit_per_unit)


def resolve_company_driver_responsibility(category: str) -> FuelFinancialResponsibilityResult:
    cat = _norm_category(category)
    if cat == CATEGORY_UNMAPPED:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
            settlement_deduction_candidate=False,
            responsible_payee_id=None,
            reason="UNMAPPED_CATEGORY",
            category=cat,
            ownership_type="company",
            provenance={"policy": "company_driver"},
        )
    if cat == CATEGORY_CASH_ADVANCE:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_DRIVER_DEDUCTION,
            settlement_deduction_candidate=True,
            responsible_payee_id=None,
            reason="COMPANY_DRIVER_CASH_ADVANCE",
            category=cat,
            ownership_type="company",
            provenance={"policy": "company_driver"},
        )
    if cat in {
        CATEGORY_FUEL,
        CATEGORY_DEF,
        CATEGORY_PRODUCT_PURCHASE,
        CATEGORY_REPAIR_OR_SERVICE,
    }:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_COMPANY_EXPENSE,
            settlement_deduction_candidate=False,
            responsible_payee_id=None,
            reason="COMPANY_OPERATING_EXPENSE",
            category=cat,
            ownership_type="company",
            provenance={"policy": "company_driver"},
        )
    if cat in {CATEGORY_TOLL, CATEGORY_LUMPER, CATEGORY_SCALE, CATEGORY_PARKING, CATEGORY_OTHER}:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
            settlement_deduction_candidate=False,
            responsible_payee_id=None,
            reason="CROSS_MODULE_POLICY_NOT_LOCKED",
            category=cat,
            ownership_type="company",
            provenance={"policy": "company_driver", "note": "preserve classification; responsibility TBD"},
        )
    return FuelFinancialResponsibilityResult(
        financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
        settlement_deduction_candidate=False,
        responsible_payee_id=None,
        reason="UNKNOWN_CATEGORY",
        category=cat,
        ownership_type="company",
        provenance={"policy": "company_driver"},
    )


def resolve_owner_operator_responsibility(
    *,
    category: str,
    owner_operator_payee_id: int | None,
    driver_id_snapshot: int | None,
    pump_unit_price: Any = None,
    quantity: Any = None,
    provider_discount_per_unit: Any = None,
    transaction_datetime: datetime | None = None,
    transaction_date: date | None = None,
    provider_timezone: str | None = None,
    oo_pricing_rules: Sequence[Mapping[str, Any]] = (),
) -> FuelFinancialResponsibilityResult:
    cat = _norm_category(category)
    if owner_operator_payee_id is None:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
            settlement_deduction_candidate=False,
            responsible_payee_id=None,
            reason="MISSING_OWNER_OPERATOR_PAYEE",
            category=cat,
            ownership_type="owner_operator",
            driver_id_snapshot=driver_id_snapshot,
            provenance={"policy": "owner_operator", "driver_not_payee": True},
        )
    if cat == CATEGORY_UNMAPPED:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
            settlement_deduction_candidate=False,
            responsible_payee_id=owner_operator_payee_id,
            reason="UNMAPPED_CATEGORY",
            category=cat,
            ownership_type="owner_operator",
            driver_id_snapshot=driver_id_snapshot,
            provenance={"policy": "owner_operator"},
        )
    if cat == CATEGORY_CASH_ADVANCE:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
            settlement_deduction_candidate=True,
            responsible_payee_id=owner_operator_payee_id,
            reason="OO_CASH_ADVANCE",
            category=cat,
            ownership_type="owner_operator",
            driver_id_snapshot=driver_id_snapshot,
            provenance={"policy": "owner_operator", "driver_not_payee": True},
        )
    if cat in {CATEGORY_TOLL, CATEGORY_LUMPER, CATEGORY_SCALE, CATEGORY_PARKING}:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
            settlement_deduction_candidate=False,
            responsible_payee_id=owner_operator_payee_id,
            reason="CROSS_MODULE_POLICY_NOT_LOCKED",
            category=cat,
            ownership_type="owner_operator",
            driver_id_snapshot=driver_id_snapshot,
            provenance={"policy": "owner_operator"},
        )
    if cat == CATEGORY_REPAIR_OR_SERVICE:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
            settlement_deduction_candidate=True,
            responsible_payee_id=owner_operator_payee_id,
            reason="OO_REPAIR_OR_SERVICE_DEFAULT",
            category=cat,
            ownership_type="owner_operator",
            driver_id_snapshot=driver_id_snapshot,
            provenance={"policy": "owner_operator"},
        )
    if cat in {CATEGORY_FUEL, CATEGORY_DEF, CATEGORY_PRODUCT_PURCHASE}:
        pricing = price_fuel_transaction_for_oo(
            owner_operator_payee_id=owner_operator_payee_id,
            ownership_type="owner_operator",
            financial_responsibility=None,
            is_company_driver=False,
            transaction_datetime=transaction_datetime,
            transaction_date=transaction_date,
            pump_unit_price=pump_unit_price,
            quantity=quantity,
            provider_discount_per_unit=provider_discount_per_unit,
            rules=oo_pricing_rules,
            provider_timezone=provider_timezone,
        )
        if pricing.requires_review or pricing.status != "CALCULATED":
            return FuelFinancialResponsibilityResult(
                financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
                settlement_deduction_candidate=False,
                responsible_payee_id=owner_operator_payee_id,
                reason=pricing.reason or pricing.status,
                category=cat,
                ownership_type="owner_operator",
                driver_id_snapshot=driver_id_snapshot,
                oo_pricing=pricing,
                provenance={"policy": "owner_operator", "oo_pricing_status": pricing.status},
            )
        retained = company_retained_provider_discount_per_unit(
            provider_discount_per_unit=pricing.provider_discount_per_unit,
            oo_benefit_per_unit=pricing.oo_benefit_per_unit,
        )
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
            settlement_deduction_candidate=True,
            responsible_payee_id=owner_operator_payee_id,
            reason="OO_FUEL_PRODUCT_PRICED",
            category=cat,
            ownership_type="owner_operator",
            driver_id_snapshot=driver_id_snapshot,
            oo_pricing=pricing,
            company_retained_discount_per_unit=retained,
            provenance={
                "policy": "owner_operator",
                "tax_treatment_for_settlement": TAX_TREATMENT_FOR_SETTLEMENT,
            },
        )
    return FuelFinancialResponsibilityResult(
        financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
        settlement_deduction_candidate=False,
        responsible_payee_id=owner_operator_payee_id,
        reason="UNKNOWN_CATEGORY",
        category=cat,
        ownership_type="owner_operator",
        driver_id_snapshot=driver_id_snapshot,
        provenance={"policy": "owner_operator"},
    )


def resolve_fuel_financial_responsibility(
    *,
    category: str,
    truck_id: int | None,
    at: datetime | None,
    ownership_history_rows: Sequence[Mapping[str, Any]] = (),
    driver_id_snapshot: int | None = None,
    is_company_driver: bool | None = None,
    pump_unit_price: Any = None,
    quantity: Any = None,
    provider_discount_per_unit: Any = None,
    transaction_date: date | None = None,
    provider_timezone: str | None = None,
    oo_pricing_rules: Sequence[Mapping[str, Any]] = (),
) -> FuelFinancialResponsibilityResult:
    """Determine Fuel financial responsibility from category + historical ownership.

    Driver snapshot does not override owner/payee for O/O units.
    """
    cat = _norm_category(category)
    if is_company_driver is True:
        return resolve_company_driver_responsibility(cat)

    ownership: HistoricalResolution = resolve_ownership_at(
        truck_id=truck_id,
        at=at,
        history_rows=ownership_history_rows,
    )
    if ownership.status != STATUS_RESOLVED or ownership.value is None:
        return FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
            settlement_deduction_candidate=False,
            responsible_payee_id=None,
            reason=ownership.review_reason or ownership.status,
            category=cat,
            driver_id_snapshot=driver_id_snapshot,
            provenance={"ownership_resolution": ownership.status},
        )

    ownership_type = str(ownership.value.get("ownership_type") or "")
    payee_id = ownership.value.get("owner_operator_payee_id")
    payee_int = None if payee_id is None else int(payee_id)

    if _is_company_ownership(ownership_type):
        return resolve_company_driver_responsibility(cat)

    if _is_oo_ownership(ownership_type):
        return resolve_owner_operator_responsibility(
            category=cat,
            owner_operator_payee_id=payee_int,
            driver_id_snapshot=driver_id_snapshot,
            pump_unit_price=pump_unit_price,
            quantity=quantity,
            provider_discount_per_unit=provider_discount_per_unit,
            transaction_datetime=at,
            transaction_date=transaction_date,
            provider_timezone=provider_timezone,
            oo_pricing_rules=oo_pricing_rules,
        )

    return FuelFinancialResponsibilityResult(
        financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
        settlement_deduction_candidate=False,
        responsible_payee_id=payee_int,
        reason="UNKNOWN_OWNERSHIP_TYPE",
        category=cat,
        ownership_type=ownership_type or None,
        driver_id_snapshot=driver_id_snapshot,
        provenance={"ownership_type": ownership_type},
    )


def evaluate_oo_fuel_pricing_modes(
    *,
    pump_unit_price: Decimal,
    provider_discount_per_unit: Decimal,
    quantity: Decimal = Decimal("1"),
) -> dict[str, OoFuelPricingResult]:
    """Convenience for tests/docs — all four locked O/O fuel pricing modes."""
    from app.services.fuel_oo_pricing import (
        MODE_FIXED_DISCOUNT,
        MODE_FULL_PROVIDER_DISCOUNT,
        MODE_NO_DISCOUNT,
        MODE_PERCENT_OF_PROVIDER_DISCOUNT,
    )

    return {
        "NO_DISCOUNT": calculate_oo_fuel_charge(
            pricing_mode=MODE_NO_DISCOUNT,
            pump_unit_price=pump_unit_price,
            quantity=quantity,
            provider_discount_per_unit=provider_discount_per_unit,
        ),
        "FULL_PROVIDER_DISCOUNT": calculate_oo_fuel_charge(
            pricing_mode=MODE_FULL_PROVIDER_DISCOUNT,
            pump_unit_price=pump_unit_price,
            quantity=quantity,
            provider_discount_per_unit=provider_discount_per_unit,
        ),
        "FIXED_CENTS": calculate_oo_fuel_charge(
            pricing_mode=MODE_FIXED_DISCOUNT,
            pump_unit_price=pump_unit_price,
            quantity=quantity,
            provider_discount_per_unit=provider_discount_per_unit,
            fixed_discount_per_unit=Decimal("0.05"),
        ),
        "PERCENT_OF_PROVIDER_DISCOUNT": calculate_oo_fuel_charge(
            pricing_mode=MODE_PERCENT_OF_PROVIDER_DISCOUNT,
            pump_unit_price=pump_unit_price,
            quantity=quantity,
            provider_discount_per_unit=provider_discount_per_unit,
            percent_of_provider_discount=Decimal("0.20"),
        ),
    }
