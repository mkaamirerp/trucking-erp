"""Fuel financial responsibility persistence + classification integration."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.fuel import FuelTransaction, FuelTransactionFinancialEvent
from app.services.fuel_charge_categories import (
    CATEGORY_CASH_ADVANCE,
    CATEGORY_DEF,
    CATEGORY_FUEL,
    CATEGORY_OTHER,
    CATEGORY_UNMAPPED,
    CLASSIFICATION_SOURCE_MANUAL,
    CLASSIFICATION_STATUS_CONFIRMED,
)
from app.services.fuel_classification_persistence import apply_classification_result
from app.services.fuel_financial_responsibility import (
    RESPONSIBILITY_COMPANY_EXPENSE,
    RESPONSIBILITY_DRIVER_DEDUCTION,
    RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
    RESPONSIBILITY_REVIEW_REQUIRED,
)
from app.services.fuel_financial_responsibility_refresh import (
    apply_financial_responsibility_result,
    cash_advance_recoverable_basis_amount,
    compute_financial_responsibility_for_transaction,
    financial_state_snapshot,
    provider_discount_per_unit_from_transaction,
    refresh_fuel_financial_responsibility_for_transaction_row,
)
from app.services.fuel_oo_pricing import MODE_FIXED_DISCOUNT
from app.services.fuel_transaction_classify import FuelTransactionClassificationResult

TENANT = 990_003


def _dt(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


def _company_hist(truck_id: int = 1104) -> list[dict]:
    return [
        {
            "id": 1,
            "truck_id": truck_id,
            "ownership_type": "company",
            "owner_operator_payee_id": None,
            "effective_from": _dt(2020, 1, 1),
            "effective_to": None,
        }
    ]


def _oo_hist(truck_id: int = 1104, payee: int = 900) -> list[dict]:
    return [
        {
            "id": 2,
            "truck_id": truck_id,
            "ownership_type": "owner_operator",
            "owner_operator_payee_id": payee,
            "effective_from": _dt(2020, 1, 1),
            "effective_to": None,
        }
    ]


def _txn(**overrides) -> FuelTransaction:
    base = {
        "id": 1,
        "tenant_id": TENANT,
        "batch_id": 1,
        "source_row_order": 1,
        "source_vendor": "BVD",
        "provider_event_type": "PURCHASE",
        "transaction_datetime_source": "2026-07-28",
        "transaction_timezone_source": "DATE_ONLY",
        "transaction_date": date(2026, 7, 28),
        "transaction_datetime": _dt(2026, 7, 28),
        "provider_raw": {},
        "truck_id": 1104,
        "classification": CATEGORY_FUEL,
        "unit_price": Decimal("3.00"),
        "quantity": Decimal("1"),
        "provider_discount_amount": Decimal("0.25"),
        "billed_amount": Decimal("2.75"),
        "tax_amount": Decimal("0.36"),
        "total_amount": Decimal("3.11"),
    }
    base.update(overrides)
    return FuelTransaction(**base)


def _oo_rule(**extra) -> dict:
    return {
        "id": 10,
        "owner_operator_payee_id": 900,
        "pricing_mode": MODE_FIXED_DISCOUNT,
        "fixed_discount_per_unit": Decimal("0.05"),
        "percent_of_provider_discount": None,
        "rule_version": "v1",
        "effective_from": _dt(2020, 1, 1),
        "effective_to": None,
        **extra,
    }


def _event_adds(db: AsyncMock) -> list[FuelTransactionFinancialEvent]:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], FuelTransactionFinancialEvent)]


def test_settlement_candidate_column_on_model() -> None:
    assert "settlement_deduction_candidate" in FuelTransaction.__table__.c
    assert "settlement_deduction_basis_amount" in FuelTransaction.__table__.c
    assert FuelTransactionFinancialEvent.__tablename__ == "fuel_transaction_financial_event"


def test_legacy_transaction_candidate_null_until_evaluated() -> None:
    txn = _txn(classification=CATEGORY_FUEL)
    assert txn.settlement_deduction_candidate is None


def test_company_fuel_candidate_false_column() -> None:
    txn = _txn(classification=CATEGORY_FUEL)
    result = compute_financial_responsibility_for_transaction(
        txn, ownership_history_rows=_company_hist(), oo_pricing_rules=[]
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.financial_responsibility == RESPONSIBILITY_COMPANY_EXPENSE
    assert txn.settlement_deduction_candidate is False
    assert txn.oo_pricing_inputs_json is None or "settlement_deduction_candidate" not in (
        txn.oo_pricing_inputs_json or {}
    )


def test_company_def_candidate_false() -> None:
    txn = _txn(classification=CATEGORY_DEF)
    result = compute_financial_responsibility_for_transaction(
        txn, ownership_history_rows=_company_hist(), oo_pricing_rules=[]
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.settlement_deduction_candidate is False


def test_company_cash_advance_candidate_true_without_oo_pricing_json() -> None:
    txn = _txn(
        classification=CATEGORY_CASH_ADVANCE,
        driver_id=501,
        principal_amount=Decimal("100.00"),
        provider_fee_amount=Decimal("3.00"),
        total_amount=Decimal("103.00"),
    )
    result = compute_financial_responsibility_for_transaction(
        txn, ownership_history_rows=_company_hist(), oo_pricing_rules=[]
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.financial_responsibility == RESPONSIBILITY_DRIVER_DEDUCTION
    assert txn.settlement_deduction_candidate is True
    assert txn.owner_operator_charge_amount is None
    assert txn.principal_amount == Decimal("100.00")
    assert txn.provider_fee_amount == Decimal("3.00")
    assert txn.total_amount == Decimal("103.00")
    assert txn.oo_pricing_mode is None
    assert txn.settlement_deduction_basis_amount == Decimal("103.0000")


def test_company_cash_advance_missing_driver_review_false_candidate() -> None:
    txn = _txn(classification=CATEGORY_CASH_ADVANCE, driver_id=None)
    result = compute_financial_responsibility_for_transaction(
        txn, ownership_history_rows=_company_hist(), oo_pricing_rules=[]
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.financial_responsibility == RESPONSIBILITY_REVIEW_REQUIRED
    assert txn.settlement_deduction_candidate is False
    assert txn.settlement_deduction_basis_amount is None


def test_oo_fuel_candidate_true_column() -> None:
    txn = _txn(classification=CATEGORY_FUEL)
    result = compute_financial_responsibility_for_transaction(
        txn,
        ownership_history_rows=_oo_hist(),
        oo_pricing_rules=[_oo_rule()],
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.financial_responsibility == RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION
    assert txn.settlement_deduction_candidate is True
    assert txn.owner_operator_payee_id == 900
    assert txn.owner_operator_charge_amount == Decimal("2.9500")
    assert txn.settlement_deduction_basis_amount is None


def test_oo_cash_advance_candidate_true_and_basis_103() -> None:
    txn = _txn(
        classification=CATEGORY_CASH_ADVANCE,
        driver_id=999,
        principal_amount=Decimal("100.00"),
        provider_fee_amount=Decimal("3.00"),
        total_amount=Decimal("103.00"),
    )
    result = compute_financial_responsibility_for_transaction(
        txn,
        ownership_history_rows=_oo_hist(),
        oo_pricing_rules=[],
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.settlement_deduction_candidate is True
    assert txn.settlement_deduction_basis_amount == Decimal("103.0000")
    assert txn.owner_operator_charge_amount is None


def test_cash_advance_basis_ignores_unrelated_fee_fields() -> None:
    """Only principal + row provider_fee — not a separate unrelated fee on another row."""
    txn = _txn(
        classification=CATEGORY_CASH_ADVANCE,
        driver_id=1,
        principal_amount=Decimal("100.00"),
        provider_fee_amount=Decimal("3.00"),
        out_of_network_fee=Decimal("50.00"),
    )
    assert cash_advance_recoverable_basis_amount(txn) == Decimal("103.0000")


def test_cash_advance_basis_decimal_safe() -> None:
    txn = _txn(
        principal_amount="100.00",
        provider_fee_amount="3.00",
    )
    basis = cash_advance_recoverable_basis_amount(txn)
    assert isinstance(basis, Decimal)
    assert basis == Decimal("103.0000")


@pytest.mark.asyncio
async def test_basis_amount_change_audited() -> None:
    txn = _txn(
        classification=CATEGORY_CASH_ADVANCE,
        driver_id=501,
        principal_amount=Decimal("100.00"),
        provider_fee_amount=Decimal("3.00"),
    )
    db = AsyncMock()
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    txn.principal_amount = Decimal("150.00")
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    events = _event_adds(db)
    assert len(events) == 2
    assert events[1].previous_settlement_deduction_basis_amount == Decimal("103.0000")
    assert events[1].new_settlement_deduction_basis_amount == Decimal("153.0000")


def test_review_required_evaluated_false_candidate() -> None:
    txn = _txn(classification=CATEGORY_UNMAPPED)
    result = compute_financial_responsibility_for_transaction(
        txn,
        ownership_history_rows=_company_hist(),
        oo_pricing_rules=[],
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.financial_responsibility == RESPONSIBILITY_REVIEW_REQUIRED
    assert txn.settlement_deduction_candidate is False


@pytest.mark.asyncio
async def test_first_evaluation_writes_financial_event() -> None:
    txn = _txn(classification=CATEGORY_FUEL)
    db = AsyncMock()
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    events = _event_adds(db)
    assert len(events) == 1
    assert events[0].previous_financial_responsibility is None
    assert events[0].new_financial_responsibility == RESPONSIBILITY_COMPANY_EXPENSE
    assert events[0].previous_settlement_deduction_candidate is None
    assert events[0].new_settlement_deduction_candidate is False


@pytest.mark.asyncio
async def test_reclassification_writes_second_event() -> None:
    txn = _txn(classification=CATEGORY_UNMAPPED)
    db = AsyncMock()
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    txn.classification = CATEGORY_CASH_ADVANCE
    txn.driver_id = 501
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    events = _event_adds(db)
    assert len(events) == 2
    assert events[1].new_financial_responsibility == RESPONSIBILITY_DRIVER_DEDUCTION
    assert events[1].new_settlement_deduction_candidate is True


@pytest.mark.asyncio
async def test_idempotent_refresh_no_duplicate_event() -> None:
    txn = _txn(classification=CATEGORY_FUEL)
    db = AsyncMock()
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_oo_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[_oo_rule()]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    assert len(_event_adds(db)) == 1


@pytest.mark.asyncio
async def test_candidate_true_to_false_audited() -> None:
    txn = _txn(classification=CATEGORY_CASH_ADVANCE, driver_id=88)
    db = AsyncMock()
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    txn.classification = CATEGORY_OTHER
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    events = _event_adds(db)
    assert events[-1].previous_settlement_deduction_candidate is True
    assert events[-1].new_settlement_deduction_candidate is False


@pytest.mark.asyncio
async def test_payee_change_audited_on_oo_fuel() -> None:
    txn = _txn(classification=CATEGORY_FUEL)
    db = AsyncMock()
    hist = _oo_hist(payee=900)
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=hist),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[_oo_rule()]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    hist[0]["owner_operator_payee_id"] = 901
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=hist),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[_oo_rule(owner_operator_payee_id=901)]),
        ):
            await refresh_fuel_financial_responsibility_for_transaction_row(db, txn)
    events = _event_adds(db)
    assert events[-1].previous_owner_operator_payee_id == 900
    assert events[-1].new_owner_operator_payee_id == 901


def test_provider_fields_unchanged_on_refresh() -> None:
    txn = _txn()
    before = (txn.billed_amount, txn.tax_amount, txn.total_amount, txn.principal_amount)
    result = compute_financial_responsibility_for_transaction(
        txn, ownership_history_rows=_oo_hist(), oo_pricing_rules=[_oo_rule()]
    )
    apply_financial_responsibility_result(txn, result)
    assert (txn.billed_amount, txn.tax_amount, txn.total_amount, txn.principal_amount) == before


def test_refresh_idempotent_apply() -> None:
    txn = _txn(classification=CATEGORY_FUEL)
    rules = [_oo_rule()]
    hist = _oo_hist()
    r1 = compute_financial_responsibility_for_transaction(txn, ownership_history_rows=hist, oo_pricing_rules=rules)
    apply_financial_responsibility_result(txn, r1)
    snap = financial_state_snapshot(txn)
    r2 = compute_financial_responsibility_for_transaction(txn, ownership_history_rows=hist, oo_pricing_rules=rules)
    assert apply_financial_responsibility_result(txn, r2) is False
    assert financial_state_snapshot(txn) == snap


@pytest.mark.asyncio
async def test_manual_classification_recomputes_financial() -> None:
    txn = _txn(classification=CATEGORY_UNMAPPED, classification_status="UNMAPPED")
    db = AsyncMock()
    result = FuelTransactionClassificationResult(
        classification=CATEGORY_CASH_ADVANCE,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=CLASSIFICATION_SOURCE_MANUAL,
        mapping_id=None,
    )
    txn.driver_id = 77
    txn.principal_amount = Decimal("100.00")
    txn.provider_fee_amount = Decimal("3.00")
    with patch(
        "app.services.fuel_financial_responsibility_refresh.load_ownership_history_rows",
        AsyncMock(return_value=_company_hist()),
    ):
        with patch(
            "app.services.fuel_financial_responsibility_refresh.load_oo_pricing_rules",
            AsyncMock(return_value=[]),
        ):
            changed = await apply_classification_result(db, txn=txn, result=result, actor_user_id="u1")
    assert changed is True
    assert txn.financial_responsibility == RESPONSIBILITY_DRIVER_DEDUCTION
    assert txn.settlement_deduction_candidate is True
    assert txn.settlement_deduction_basis_amount == Decimal("103.0000")


def test_driver_deduction_uses_driver_id_not_owner_operator_payee() -> None:
    txn = _txn(
        classification=CATEGORY_CASH_ADVANCE,
        driver_id=501,
        principal_amount=Decimal("100.00"),
        provider_fee_amount=Decimal("3.00"),
    )
    result = compute_financial_responsibility_for_transaction(
        txn, ownership_history_rows=_company_hist(), oo_pricing_rules=[]
    )
    apply_financial_responsibility_result(txn, result)
    assert txn.owner_operator_payee_id is None
    assert txn.driver_id == 501


def test_no_settlement_module_import_in_refresh() -> None:
    import app.services.fuel_financial_responsibility_refresh as mod

    assert "settlement" not in mod.__file__.lower()
