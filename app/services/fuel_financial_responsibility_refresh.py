"""Persist Fuel financial responsibility on canonical transactions (no Settlement/Payroll)."""

from __future__ import annotations

import logging
from dataclasses import replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import (
    FuelOwnerOperatorPricingRule,
    FuelTransaction,
    FuelTransactionFinancialEvent,
)
from app.models.truck_history import TruckOwnershipHistory
from app.services.fuel_charge_categories import CATEGORY_CASH_ADVANCE
from app.services.fuel_financial_responsibility import (
    RESPONSIBILITY_DRIVER_DEDUCTION,
    RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
    RESPONSIBILITY_REVIEW_REQUIRED,
    FuelFinancialResponsibilityResult,
    resolve_fuel_financial_responsibility,
)
from app.services.fuel_historical_resolution import resolution_point_in_time
from app.services.fuel_money import quantize_money, quantize_unit_price, to_decimal
from app.services.fuel_oo_pricing import (
    STATUS_CALCULATED,
    oo_pricing_result_as_derived_fields,
)

logger = logging.getLogger(__name__)

FINANCIAL_EVENT_SOURCE_REFRESH = "FINANCIAL_RESPONSIBILITY_REFRESH"

# Provider/source columns refresh must never write.
_PROVIDER_IMMUTABLE_SNAPSHOT_FIELDS = frozenset(
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
        "principal_amount",
        "provider_fee_amount",
        "quantity",
        "currency",
        "currency_raw",
    }
)


def provider_discount_per_unit_from_transaction(txn: FuelTransaction) -> Decimal | None:
    """Derive per-unit provider discount from canonical row; never infer from pump alone."""
    if txn.quantity is None or txn.quantity == 0:
        return None
    if txn.provider_discount_amount is not None:
        return quantize_unit_price(to_decimal(txn.provider_discount_amount) / to_decimal(txn.quantity))
    return None


def _ownership_row_dict(row: TruckOwnershipHistory) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "truck_id": int(row.truck_id),
        "ownership_type": row.ownership_type,
        "owner_operator_payee_id": row.owner_operator_payee_id,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
    }


def _oo_rule_dict(row: FuelOwnerOperatorPricingRule) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "owner_operator_payee_id": int(row.owner_operator_payee_id),
        "pricing_mode": row.pricing_mode,
        "fixed_discount_per_unit": row.fixed_discount_per_unit,
        "percent_of_provider_discount": row.percent_of_provider_discount,
        "rule_version": row.rule_version,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
    }


def _money_key(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(quantize_money(value))


def cash_advance_recoverable_basis_amount(txn: FuelTransaction) -> Decimal | None:
    """Locked: principal + directly attributable provider_fee on this row (Decimal only)."""
    if txn.principal_amount is None:
        return None
    principal = to_decimal(txn.principal_amount)
    fee = Decimal("0") if txn.provider_fee_amount is None else to_decimal(txn.provider_fee_amount)
    return quantize_money(principal + fee)


def settlement_deduction_basis_for_result(
    txn: FuelTransaction,
    result: FuelFinancialResponsibilityResult,
) -> Decimal | None:
    """Fuel-owned recoverable basis; CASH_ADVANCE only (not O/O fuel tax-final amounts)."""
    cat = (result.category or txn.classification or "").strip().upper()
    if cat != CATEGORY_CASH_ADVANCE:
        return None
    if not result.settlement_deduction_candidate:
        return None
    if result.financial_responsibility not in (
        RESPONSIBILITY_DRIVER_DEDUCTION,
        RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
    ):
        return None
    return cash_advance_recoverable_basis_amount(txn)


def financial_state_snapshot(txn: FuelTransaction) -> dict[str, Any]:
    """Operational derived financial state (authoritative columns only)."""
    return {
        "financial_responsibility": txn.financial_responsibility,
        "settlement_deduction_candidate": txn.settlement_deduction_candidate,
        "settlement_deduction_basis_amount": _money_key(txn.settlement_deduction_basis_amount),
        "owner_operator_payee_id": txn.owner_operator_payee_id,
        "driver_id": txn.driver_id,
        "owner_operator_charge_amount": _money_key(txn.owner_operator_charge_amount),
        "oo_pricing_mode": txn.oo_pricing_mode,
        "oo_pricing_status": txn.oo_pricing_status,
        "oo_charge_unit_price": (
            None
            if txn.oo_charge_unit_price is None
            else str(quantize_unit_price(txn.oo_charge_unit_price))
        ),
    }


def _merge_oo_provenance_only(txn: FuelTransaction, result: FuelFinancialResponsibilityResult) -> dict[str, Any]:
    """O/O pricing JSON holds calculator inputs + policy notes — not settlement candidate authority."""
    base = dict(txn.oo_pricing_inputs_json or {})
    base.pop("settlement_deduction_candidate", None)
    provenance = dict(result.provenance or {})
    provenance["financial_responsibility_reason"] = result.reason
    provenance["category"] = result.category
    base["financial_responsibility_provenance"] = provenance
    return base


def _clear_oo_pricing_derived(txn: FuelTransaction) -> None:
    txn.owner_operator_charge_amount = None
    txn.oo_pricing_mode = None
    txn.oo_pricing_rule_id = None
    txn.oo_pricing_rule_version = None
    txn.oo_charge_unit_price = None
    txn.oo_benefit_per_unit = None
    txn.oo_pricing_status = None
    txn.oo_pricing_reason = None


def _candidate_column_value(result: FuelFinancialResponsibilityResult) -> bool:
    """After evaluation, candidate is always explicit TRUE/FALSE (never NULL)."""
    return bool(result.settlement_deduction_candidate)


async def append_financial_event_if_changed(
    db: AsyncSession,
    *,
    txn: FuelTransaction,
    previous: dict[str, Any],
    new: dict[str, Any],
    reason_code: str | None,
    actor_user_id: str | None = None,
    source: str = FINANCIAL_EVENT_SOURCE_REFRESH,
) -> bool:
    if previous == new:
        return False
    db.add(
        FuelTransactionFinancialEvent(
            tenant_id=int(txn.tenant_id),
            fuel_transaction_id=int(txn.id),
            previous_financial_responsibility=previous.get("financial_responsibility"),
            new_financial_responsibility=new.get("financial_responsibility"),
            previous_settlement_deduction_candidate=previous.get("settlement_deduction_candidate"),
            new_settlement_deduction_candidate=new.get("settlement_deduction_candidate"),
            previous_owner_operator_payee_id=previous.get("owner_operator_payee_id"),
            new_owner_operator_payee_id=new.get("owner_operator_payee_id"),
            previous_driver_id=previous.get("driver_id"),
            new_driver_id=new.get("driver_id"),
            previous_owner_operator_charge_amount=(
                Decimal(previous["owner_operator_charge_amount"])
                if previous.get("owner_operator_charge_amount") is not None
                else None
            ),
            new_owner_operator_charge_amount=(
                Decimal(new["owner_operator_charge_amount"])
                if new.get("owner_operator_charge_amount") is not None
                else None
            ),
            previous_oo_charge_unit_price=(
                Decimal(previous["oo_charge_unit_price"])
                if previous.get("oo_charge_unit_price") is not None
                else None
            ),
            new_oo_charge_unit_price=(
                Decimal(new["oo_charge_unit_price"])
                if new.get("oo_charge_unit_price") is not None
                else None
            ),
            previous_settlement_deduction_basis_amount=(
                Decimal(previous["settlement_deduction_basis_amount"])
                if previous.get("settlement_deduction_basis_amount") is not None
                else None
            ),
            new_settlement_deduction_basis_amount=(
                Decimal(new["settlement_deduction_basis_amount"])
                if new.get("settlement_deduction_basis_amount") is not None
                else None
            ),
            reason_code=reason_code,
            source=source,
            metadata_json={
                "previous": previous,
                "new": new,
                "oo_pricing_mode_previous": previous.get("oo_pricing_mode"),
                "oo_pricing_mode_new": new.get("oo_pricing_mode"),
            },
            actor_user_id=actor_user_id,
        )
    )
    return True


def apply_financial_responsibility_result(
    txn: FuelTransaction,
    result: FuelFinancialResponsibilityResult,
) -> bool:
    """Write derived financial fields only. Returns True when operational snapshot changed."""
    previous = financial_state_snapshot(txn)
    prior_inputs_json = txn.oo_pricing_inputs_json
    provider_before = {f: getattr(txn, f) for f in _PROVIDER_IMMUTABLE_SNAPSHOT_FIELDS}

    txn.financial_responsibility = result.financial_responsibility
    txn.settlement_deduction_candidate = _candidate_column_value(result)

    if result.financial_responsibility == RESPONSIBILITY_REVIEW_REQUIRED:
        txn.settlement_deduction_basis_amount = None
        txn.owner_operator_payee_id = result.responsible_payee_id
        _clear_oo_pricing_derived(txn)
    elif result.financial_responsibility == RESPONSIBILITY_DRIVER_DEDUCTION:
        txn.owner_operator_payee_id = None
        _clear_oo_pricing_derived(txn)
        txn.settlement_deduction_basis_amount = settlement_deduction_basis_for_result(txn, result)
    else:
        if result.responsible_payee_id is not None:
            txn.owner_operator_payee_id = int(result.responsible_payee_id)
        else:
            txn.owner_operator_payee_id = None

        if result.oo_pricing is not None and result.oo_pricing.status == STATUS_CALCULATED:
            derived = oo_pricing_result_as_derived_fields(result.oo_pricing)
            pricing_inputs = derived.pop("oo_pricing_inputs_json", None)
            for key, val in derived.items():
                setattr(txn, key, val)
            if pricing_inputs is not None:
                merged_inputs = _merge_oo_provenance_only(txn, result)
                merged_inputs["oo_pricing_calc_inputs"] = pricing_inputs
                txn.oo_pricing_inputs_json = merged_inputs
        else:
            _clear_oo_pricing_derived(txn)
        if result.financial_responsibility == RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION:
            txn.settlement_deduction_basis_amount = settlement_deduction_basis_for_result(txn, result)
        else:
            txn.settlement_deduction_basis_amount = None

    if result.financial_responsibility == RESPONSIBILITY_REVIEW_REQUIRED:
        pass  # basis already cleared
    elif result.financial_responsibility not in (
        RESPONSIBILITY_DRIVER_DEDUCTION,
        RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
    ):
        txn.settlement_deduction_basis_amount = None

    new_snap = financial_state_snapshot(txn)
    if previous == new_snap:
        txn.oo_pricing_inputs_json = prior_inputs_json
        return False

    if txn.oo_pricing_inputs_json is prior_inputs_json or txn.oo_pricing_inputs_json is None:
        txn.oo_pricing_inputs_json = _merge_oo_provenance_only(txn, result)
        if isinstance(prior_inputs_json, dict) and "oo_pricing_calc_inputs" in prior_inputs_json:
            txn.oo_pricing_inputs_json["oo_pricing_calc_inputs"] = prior_inputs_json["oo_pricing_calc_inputs"]

    provider_after = {f: getattr(txn, f) for f in _PROVIDER_IMMUTABLE_SNAPSHOT_FIELDS}
    if provider_before != provider_after:
        raise RuntimeError("Financial refresh mutated provider/source amount fields")

    return True


def compute_financial_responsibility_for_transaction(
    txn: FuelTransaction,
    *,
    ownership_history_rows: Sequence[Mapping[str, Any]],
    oo_pricing_rules: Sequence[Mapping[str, Any]],
) -> FuelFinancialResponsibilityResult:
    """Pure decision from current txn classification + historical ownership."""
    at = resolution_point_in_time(
        transaction_datetime=txn.transaction_datetime,
        transaction_date=txn.transaction_date,
    )
    category = txn.classification or "UNMAPPED"
    result = resolve_fuel_financial_responsibility(
        category=category,
        truck_id=txn.truck_id,
        at=at,
        ownership_history_rows=ownership_history_rows,
        driver_id_snapshot=txn.driver_id,
        is_company_driver=None,
        pump_unit_price=txn.unit_price,
        quantity=txn.quantity,
        provider_discount_per_unit=provider_discount_per_unit_from_transaction(txn),
        transaction_date=txn.transaction_date,
        provider_timezone=txn.transaction_timezone,
        oo_pricing_rules=oo_pricing_rules,
    )

    if result.financial_responsibility == RESPONSIBILITY_DRIVER_DEDUCTION:
        if txn.driver_id is None:
            return replace(
                result,
                financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
                settlement_deduction_candidate=False,
                responsible_payee_id=None,
                reason="MISSING_DRIVER_PAYEE",
            )
        return replace(
            result,
            responsible_payee_id=int(txn.driver_id),
            settlement_deduction_candidate=True,
            reason=result.reason or "COMPANY_DRIVER_CASH_ADVANCE",
        )

    return result


async def load_ownership_history_rows(
    db: AsyncSession,
    *,
    tenant_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(TruckOwnershipHistory).where(TruckOwnershipHistory.tenant_id == tenant_id)
        )
    ).all()
    return [_ownership_row_dict(r) for r in rows]


async def load_oo_pricing_rules(
    db: AsyncSession,
    *,
    tenant_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(FuelOwnerOperatorPricingRule).where(FuelOwnerOperatorPricingRule.tenant_id == tenant_id)
        )
    ).all()
    return [_oo_rule_dict(r) for r in rows]


async def refresh_fuel_financial_responsibility_for_transaction_row(
    db: AsyncSession,
    txn: FuelTransaction,
    *,
    ownership_history_rows: Sequence[Mapping[str, Any]] | None = None,
    oo_pricing_rules: Sequence[Mapping[str, Any]] | None = None,
    actor_user_id: str | None = None,
) -> FuelFinancialResponsibilityResult:
    """Recompute and persist derived financial fields for one canonical transaction."""
    previous = financial_state_snapshot(txn)
    try:
        if ownership_history_rows is None:
            ownership_history_rows = await load_ownership_history_rows(db, tenant_id=txn.tenant_id)
        if oo_pricing_rules is None:
            oo_pricing_rules = await load_oo_pricing_rules(db, tenant_id=txn.tenant_id)
        result = compute_financial_responsibility_for_transaction(
            txn,
            ownership_history_rows=ownership_history_rows,
            oo_pricing_rules=oo_pricing_rules,
        )
        changed = apply_financial_responsibility_result(txn, result)
        new_state = financial_state_snapshot(txn)
        if changed:
            await append_financial_event_if_changed(
                db,
                txn=txn,
                previous=previous,
                new=new_state,
                reason_code=result.reason,
                actor_user_id=actor_user_id,
            )
        return result
    except Exception:
        logger.exception(
            "fuel financial responsibility refresh failed tenant_id=%s txn_id=%s",
            txn.tenant_id,
            txn.id,
        )
        fail_result = FuelFinancialResponsibilityResult(
            financial_responsibility=RESPONSIBILITY_REVIEW_REQUIRED,
            settlement_deduction_candidate=False,
            responsible_payee_id=None,
            reason="FINANCIAL_REFRESH_FAILED",
            category=(txn.classification or "UNMAPPED").strip().upper(),
        )
        changed = apply_financial_responsibility_result(txn, fail_result)
        new_state = financial_state_snapshot(txn)
        if changed:
            await append_financial_event_if_changed(
                db,
                txn=txn,
                previous=previous,
                new=new_state,
                reason_code="FINANCIAL_REFRESH_FAILED",
                actor_user_id=actor_user_id,
            )
        return fail_result


async def refresh_fuel_financial_responsibility_for_transaction(
    db: AsyncSession,
    *,
    tenant_id: int,
    transaction_id: int,
    actor_user_id: str | None = None,
) -> FuelFinancialResponsibilityResult | None:
    txn = await db.scalar(
        select(FuelTransaction).where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.id == transaction_id,
        )
    )
    if txn is None:
        return None
    return await refresh_fuel_financial_responsibility_for_transaction_row(
        db, txn, actor_user_id=actor_user_id
    )
