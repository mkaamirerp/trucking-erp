"""Fuel Segment 9 — deterministic reconciliation engine.

Answers: do reviewed canonical transactions mathematically reconcile to
provider-declared control totals on ``fuel_source_controls``?

AI has zero authority. Decimal only. No settlement/posting (Segment 10+).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelSourceBatch, FuelSourceControl, FuelTransaction
from app.services.audit_events import write_audit_event
from app.services.fuel_canonical import (
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_READY_FOR_RECONCILIATION,
    BATCH_STATUS_RECONCILED,
    BATCH_STATUS_RECONCILIATION_FAILED,
    PROVIDER_EVENT_OTHER,
    PROVIDER_EVENT_UNKNOWN,
    ROW_REVIEW_CONFIRMED,
)
from app.services.fuel_controls import (
    CONTROL_SCOPE_BATCH,
    CONTROL_SCOPE_CARD,
    CONTROL_SCOPE_CURRENCY,
    CONTROL_SCOPE_GROUP,
    CONTROL_SCOPE_INVOICE,
    CONTROL_SCOPE_OTHER,
    CONTROL_SCOPE_PRODUCT,
    CONTROL_SCOPE_STATEMENT,
    CONTROL_SCOPE_UNIT,
    CONTROL_SCOPE_UNKNOWN,
    CONTROL_TYPE_CARD_TOTAL,
    CONTROL_TYPE_CURRENCY_TOTAL,
    CONTROL_TYPE_DISCOUNT_CONTROL,
    CONTROL_TYPE_GROUP_SUBTOTAL,
    CONTROL_TYPE_INVOICE_SUMMARY,
    CONTROL_TYPE_INVOICE_TOTAL,
    CONTROL_TYPE_OTHER,
    CONTROL_TYPE_PRODUCT_SUBTOTAL,
    CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
    CONTROL_TYPE_STATEMENT_TOTAL,
    CONTROL_TYPE_TAX_CONTROL,
    CONTROL_TYPE_UNIT_SUBTOTAL,
    CONTROL_TYPE_UNKNOWN,
    CONTROL_TYPE_VARIANCE,
    assert_no_source_row_double_count,
)
from app.services.fuel_money import FuelFloatForbidden, decimal_json, quantize_money

MODULE = "fuel"

GATE_PASS = "PASS"
GATE_FAIL = "FAIL"
GATE_BLOCKED = "BLOCKED"
GATE_SKIPPED = "SKIPPED"

OUTCOME_RECONCILED = "RECONCILED"
OUTCOME_RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
OUTCOME_BLOCKED = "BLOCKED"

# Controls that declare a total which must equal a scoped sum of transaction totals.
AMOUNT_CONTROL_TYPES: frozenset[str] = frozenset(
    {
        CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
        CONTROL_TYPE_INVOICE_TOTAL,
        CONTROL_TYPE_INVOICE_SUMMARY,
        CONTROL_TYPE_STATEMENT_TOTAL,
        CONTROL_TYPE_CURRENCY_TOTAL,
        CONTROL_TYPE_CARD_TOTAL,
        CONTROL_TYPE_UNIT_SUBTOTAL,
        CONTROL_TYPE_GROUP_SUBTOTAL,
        CONTROL_TYPE_PRODUCT_SUBTOTAL,
        CONTROL_TYPE_DISCOUNT_CONTROL,
    }
)

BATCH_LEVEL_CONTROL_TYPES: frozenset[str] = frozenset(
    {
        CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
        CONTROL_TYPE_INVOICE_TOTAL,
        CONTROL_TYPE_INVOICE_SUMMARY,
        CONTROL_TYPE_STATEMENT_TOTAL,
    }
)

TAX_AMOUNT_FIELDS: tuple[str, ...] = (
    "tax_amount",
    "hst_amount",
    "gst_amount",
    "pst_amount",
    "qst_amount",
)

ZERO = Decimal("0.0000")


class FuelReconciliationError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class ReconciliationGateResult:
    gate_id: str
    control_type: str
    control_id: int | None
    scope_key: str | None
    currency: str | None
    declared_amount: Decimal | None
    computed_amount: Decimal | None
    difference: Decimal | None
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "control_type": self.control_type,
            "control_id": self.control_id,
            "scope_key": self.scope_key,
            "currency": self.currency,
            "declared_amount": decimal_json(self.declared_amount),
            "computed_amount": decimal_json(self.computed_amount),
            "difference": decimal_json(self.difference),
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class ReconciliationReport:
    outcome: str
    batch_id: int
    tenant_id: int
    provider_code: str
    transaction_count: int
    control_count: int
    gates: list[ReconciliationGateResult] = field(default_factory=list)
    unexplained_variances: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    currencies: list[str] = field(default_factory=list)
    validated_totals_by_currency: dict[str, str] = field(default_factory=dict)
    provider_totals_by_currency: dict[str, str] = field(default_factory=dict)
    finalization_implemented: bool = False
    financial_responsibility_implemented: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "batch_id": self.batch_id,
            "tenant_id": self.tenant_id,
            "provider_code": self.provider_code,
            "transaction_count": self.transaction_count,
            "control_count": self.control_count,
            "gates": [g.to_dict() for g in self.gates],
            "unexplained_variances": self.unexplained_variances,
            "blockers": list(self.blockers),
            "currencies": list(self.currencies),
            "validated_totals_by_currency": dict(self.validated_totals_by_currency),
            "provider_totals_by_currency": dict(self.provider_totals_by_currency),
            "finalization_implemented": self.finalization_implemented,
            "financial_responsibility_implemented": self.financial_responsibility_implemented,
            "ai_authority": False,
        }


def _money(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return quantize_money(value)


def _currency_key(raw: str | None) -> str:
    text = (raw or "").strip().upper()
    return text if text else "_NONE_"


def _norm_scope(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text if text else None


def sum_transaction_totals(
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
    *,
    currency: str | None = None,
    card_or_account_id: str | None = None,
    unit_number: str | None = None,
    product: str | None = None,
    invoice_number: str | None = None,
    group_key: str | None = None,
) -> Decimal:
    """Signed sum of canonical total_amount for matching transactions."""
    total = ZERO
    want_ccy = None if currency is None else _currency_key(currency)
    want_card = _norm_scope(card_or_account_id)
    want_unit = _norm_scope(unit_number)
    want_product = _norm_scope(product)
    want_invoice = _norm_scope(invoice_number)
    want_group = _norm_scope(group_key)
    for txn in transactions:
        if not _txn_matches_filters(
            txn,
            want_ccy=want_ccy,
            want_card=want_card,
            want_unit=want_unit,
            want_product=want_product,
            want_invoice=want_invoice,
            want_group=want_group,
        ):
            continue
        amount = txn.get("total_amount") if isinstance(txn, Mapping) else txn.total_amount
        if amount is None:
            continue
        total += _money(amount)
    return quantize_money(total)


def _txn_attr(txn: FuelTransaction | Mapping[str, Any], name: str) -> Any:
    if isinstance(txn, Mapping):
        return txn.get(name)
    return getattr(txn, name, None)


def _txn_provider_raw(txn: FuelTransaction | Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _txn_attr(txn, "provider_raw")
    return raw if isinstance(raw, Mapping) else {}


def _txn_invoice_number(txn: FuelTransaction | Mapping[str, Any]) -> str | None:
    direct = _norm_scope(
        None if _txn_attr(txn, "invoice_number") is None else str(_txn_attr(txn, "invoice_number"))
    )
    if direct:
        return direct
    raw = _txn_provider_raw(txn)
    for key in ("invoice_number", "Invoice", "invoice"):
        val = raw.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _txn_group_key(txn: FuelTransaction | Mapping[str, Any]) -> str | None:
    raw = _txn_provider_raw(txn)
    for key in ("group_key", "group", "Group", "group_id"):
        val = raw.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _txn_matches_filters(
    txn: FuelTransaction | Mapping[str, Any],
    *,
    want_ccy: str | None,
    want_card: str | None,
    want_unit: str | None,
    want_product: str | None,
    want_invoice: str | None,
    want_group: str | None,
) -> bool:
    ccy = _txn_attr(txn, "currency")
    card = _txn_attr(txn, "card_or_account_id")
    unit = _txn_attr(txn, "unit_number_snapshot")
    prod = _txn_attr(txn, "product") or _txn_attr(txn, "product_code_raw")
    if want_ccy is not None and _currency_key(None if ccy is None else str(ccy)) != want_ccy:
        return False
    if want_card is not None and _norm_scope(None if card is None else str(card)) != want_card:
        return False
    if want_unit is not None and _norm_scope(None if unit is None else str(unit)) != want_unit:
        return False
    if want_product is not None and _norm_scope(None if prod is None else str(prod)) != want_product:
        return False
    if want_invoice is not None and _txn_invoice_number(txn) != want_invoice:
        return False
    if want_group is not None and _txn_group_key(txn) != want_group:
        return False
    return True


def sum_transaction_tax_field(
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
    *,
    field_name: str,
    currency: str | None = None,
) -> Decimal:
    total = ZERO
    want_ccy = None if currency is None else _currency_key(currency)
    for txn in transactions:
        if isinstance(txn, Mapping):
            ccy = txn.get("currency")
            amount = txn.get(field_name)
        else:
            ccy = txn.currency
            amount = getattr(txn, field_name, None)
        if want_ccy is not None and _currency_key(None if ccy is None else str(ccy)) != want_ccy:
            continue
        if amount is None:
            continue
        total += _money(amount)
    return quantize_money(total)


def _control_attr(control: FuelSourceControl | Mapping[str, Any], name: str) -> Any:
    if isinstance(control, Mapping):
        return control.get(name)
    return getattr(control, name)


def _control_id(control: FuelSourceControl | Mapping[str, Any]) -> int | None:
    raw = _control_attr(control, "id")
    return int(raw) if raw is not None else None


def _infer_tax_field(control: FuelSourceControl | Mapping[str, Any]) -> str | None:
    """Map a TAX_CONTROL to a transaction tax column when evidenced."""
    label = " ".join(
        str(x or "")
        for x in (
            _control_attr(control, "control_label_raw"),
            _control_attr(control, "control_type_raw"),
            _control_attr(control, "provider_control_identity"),
        )
    ).upper()
    for token, field_name in (
        ("HST", "hst_amount"),
        ("GST", "gst_amount"),
        ("PST", "pst_amount"),
        ("QST", "qst_amount"),
    ):
        if token in label:
            return field_name
    for field_name in ("hst_amount", "gst_amount", "pst_amount", "qst_amount", "tax_amount"):
        if _control_attr(control, field_name) is not None:
            return field_name
    return "tax_amount"


def _control_scope_token(control: FuelSourceControl | Mapping[str, Any]) -> str:
    raw = _control_attr(control, "control_scope")
    token = _norm_scope(None if raw is None else str(raw))
    return (token or CONTROL_SCOPE_UNKNOWN).upper()


def _distinct_invoice_numbers_among_controls(
    controls: Sequence[FuelSourceControl | Mapping[str, Any]],
) -> set[str]:
    out: set[str] = set()
    for ctrl in controls:
        ctype = str(_control_attr(ctrl, "control_type") or "")
        if ctype not in {
            CONTROL_TYPE_INVOICE_TOTAL,
            CONTROL_TYPE_INVOICE_SUMMARY,
            CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
            CONTROL_TYPE_STATEMENT_TOTAL,
        }:
            continue
        inv = _norm_scope(
            None
            if _control_attr(ctrl, "invoice_number") is None
            else str(_control_attr(ctrl, "invoice_number"))
        )
        if inv:
            out.add(inv)
    return out


def _txns_have_any_invoice_identity(
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
) -> bool:
    return any(_txn_invoice_number(t) for t in transactions)


def _txns_have_any_group_identity(
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
) -> bool:
    return any(_txn_group_key(t) for t in transactions)


def _resolve_declared_total_selection(
    control: FuelSourceControl | Mapping[str, Any],
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
    *,
    all_controls: Sequence[FuelSourceControl | Mapping[str, Any]],
    control_type: str,
) -> tuple[str | None, dict[str, str | None] | None]:
    """Return (error_reason, filter_kwargs) for invoice/statement/provider-declared totals.

    Never guesses. Batch-wide only when scope is explicitly BATCH (or currency-only
    batch-wide with no conflicting invoice partitions).
    """
    scope = _control_scope_token(control)
    currency = _control_attr(control, "currency")
    invoice = _norm_scope(
        None
        if _control_attr(control, "invoice_number") is None
        else str(_control_attr(control, "invoice_number"))
    )
    card = _norm_scope(
        None
        if _control_attr(control, "scope_card_or_account_id") is None
        else str(_control_attr(control, "scope_card_or_account_id"))
    )
    unit = _norm_scope(
        None
        if _control_attr(control, "scope_unit_number_snapshot") is None
        else str(_control_attr(control, "scope_unit_number_snapshot"))
    )

    if scope in {CONTROL_SCOPE_UNKNOWN, CONTROL_SCOPE_OTHER}:
        return "DECLARED_TOTAL_SCOPE_AMBIGUOUS", None

    # Explicit non-batch scopes must carry their keys.
    if scope == CONTROL_SCOPE_CARD:
        if not card:
            return "DECLARED_TOTAL_CARD_SCOPE_MISSING_CARD", None
        return None, {
            "currency": None if currency is None else str(currency),
            "card_or_account_id": card,
        }
    if scope == CONTROL_SCOPE_UNIT:
        if not unit:
            return "DECLARED_TOTAL_UNIT_SCOPE_MISSING_UNIT", None
        return None, {
            "currency": None if currency is None else str(currency),
            "unit_number": unit,
        }
    if scope == CONTROL_SCOPE_CURRENCY:
        if currency is None:
            return "DECLARED_TOTAL_CURRENCY_SCOPE_MISSING_CURRENCY", None
        return None, {"currency": str(currency)}

    if control_type in {
        CONTROL_TYPE_INVOICE_TOTAL,
        CONTROL_TYPE_INVOICE_SUMMARY,
    } or scope == CONTROL_SCOPE_INVOICE:
        if scope == CONTROL_SCOPE_BATCH:
            return None, {"currency": None if currency is None else str(currency)}
        if scope == CONTROL_SCOPE_CURRENCY:
            if currency is None:
                return "INVOICE_TOTAL_CURRENCY_SCOPE_MISSING_CURRENCY", None
            return None, {"currency": str(currency)}
        if scope != CONTROL_SCOPE_INVOICE:
            return "INVOICE_TOTAL_SCOPE_NOT_DETERMINISTIC", None
        if not invoice:
            return "INVOICE_SCOPE_MISSING_INVOICE_NUMBER", None
        distinct = _distinct_invoice_numbers_among_controls(all_controls)
        txn_partitioned = _txns_have_any_invoice_identity(transactions)
        if len(distinct) > 1 and not txn_partitioned:
            return "MULTI_INVOICE_SCOPE_WITHOUT_TXN_PARTITION", None
        if txn_partitioned:
            return None, {
                "currency": None if currency is None else str(currency),
                "invoice_number": invoice,
            }
        # Single-invoice batch: all transactions belong to that invoice.
        return None, {
            "currency": None if currency is None else str(currency),
            "invoice_number": None,
        }

    if control_type == CONTROL_TYPE_STATEMENT_TOTAL or scope == CONTROL_SCOPE_STATEMENT:
        if scope == CONTROL_SCOPE_BATCH:
            return None, {"currency": None if currency is None else str(currency)}
        if scope == CONTROL_SCOPE_CURRENCY:
            if currency is None:
                return "STATEMENT_TOTAL_CURRENCY_SCOPE_MISSING_CURRENCY", None
            return None, {"currency": str(currency)}
        if scope != CONTROL_SCOPE_STATEMENT:
            return "STATEMENT_TOTAL_SCOPE_NOT_DETERMINISTIC", None
        if invoice and _txns_have_any_invoice_identity(transactions):
            return None, {
                "currency": None if currency is None else str(currency),
                "invoice_number": invoice,
            }
        if invoice:
            distinct = _distinct_invoice_numbers_among_controls(all_controls)
            if len(distinct) > 1:
                return "MULTI_STATEMENT_SCOPE_WITHOUT_TXN_PARTITION", None
        return None, {"currency": None if currency is None else str(currency)}

    if control_type == CONTROL_TYPE_PROVIDER_DECLARED_TOTAL:
        if scope == CONTROL_SCOPE_BATCH or (
            scope == CONTROL_SCOPE_CURRENCY and currency is not None
        ):
            return None, {"currency": None if currency is None else str(currency)}
        if scope == CONTROL_SCOPE_INVOICE:
            if not invoice:
                return "PROVIDER_DECLARED_INVOICE_SCOPE_MISSING_INVOICE", None
            distinct = _distinct_invoice_numbers_among_controls(all_controls)
            if len(distinct) > 1 and not _txns_have_any_invoice_identity(transactions):
                return "MULTI_INVOICE_SCOPE_WITHOUT_TXN_PARTITION", None
            if _txns_have_any_invoice_identity(transactions):
                return None, {
                    "currency": None if currency is None else str(currency),
                    "invoice_number": invoice,
                }
            return None, {"currency": None if currency is None else str(currency)}
        return "PROVIDER_DECLARED_SCOPE_NOT_DETERMINISTIC", None

    # Remaining batch-level types with explicit BATCH scope.
    if scope == CONTROL_SCOPE_BATCH:
        return None, {"currency": None if currency is None else str(currency)}

    return "DECLARED_TOTAL_SCOPE_NOT_DETERMINISTIC", None


def evaluate_control_gate(
    control: FuelSourceControl | Mapping[str, Any],
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
    *,
    all_controls: Sequence[FuelSourceControl | Mapping[str, Any]] | None = None,
) -> ReconciliationGateResult:
    """Evaluate one control against transactions.

    VARIANCE rows are provider evidence only. They never force a PASS when
    ``declared_amount - calculated_amount != 0``. Until a provider-specific
    rounding/tolerance policy is proven, any nonzero difference is FAIL.
    """
    controls_ctx = list(all_controls) if all_controls is not None else [control]
    control_type = str(_control_attr(control, "control_type") or CONTROL_TYPE_UNKNOWN)
    cid = _control_id(control)
    currency = _control_attr(control, "currency")
    declared_raw = _control_attr(control, "declared_amount")
    gate_id = f"{control_type}:{cid or 'new'}"

    if control_type == CONTROL_TYPE_VARIANCE:
        # Preserve provider-declared variance evidence. Do not use it to balance.
        return ReconciliationGateResult(
            gate_id=gate_id,
            control_type=control_type,
            control_id=cid,
            scope_key="PROVIDER_VARIANCE_EVIDENCE",
            currency=None if currency is None else str(currency),
            declared_amount=None if declared_raw is None else quantize_money(declared_raw),
            computed_amount=None,
            difference=None,
            status=GATE_SKIPPED,
            reason="PROVIDER_VARIANCE_EVIDENCE_ONLY_DOES_NOT_FORCE_PASS",
        )

    if control_type in {CONTROL_TYPE_UNKNOWN, CONTROL_TYPE_OTHER}:
        return ReconciliationGateResult(
            gate_id=gate_id,
            control_type=control_type,
            control_id=cid,
            scope_key=None,
            currency=None if currency is None else str(currency),
            declared_amount=None if declared_raw is None else quantize_money(declared_raw),
            computed_amount=None,
            difference=None,
            status=GATE_BLOCKED,
            reason="UNKNOWN_OR_OTHER_CONTROL_BLOCKS_RECONCILIATION",
        )

    if declared_raw is None:
        return ReconciliationGateResult(
            gate_id=gate_id,
            control_type=control_type,
            control_id=cid,
            scope_key=None,
            currency=None if currency is None else str(currency),
            declared_amount=None,
            computed_amount=None,
            difference=None,
            status=GATE_BLOCKED,
            reason="CONTROL_DECLARED_AMOUNT_MISSING",
        )

    declared = quantize_money(declared_raw)
    scope_key: str | None = None
    computed: Decimal

    if control_type in BATCH_LEVEL_CONTROL_TYPES:
        if currency is None:
            distinct = {
                _currency_key(
                    None
                    if _txn_attr(t, "currency") is None
                    else str(_txn_attr(t, "currency"))
                )
                for t in transactions
                if _txn_attr(t, "currency")
            }
            if len(distinct) > 1 and _control_scope_token(control) != CONTROL_SCOPE_CURRENCY:
                # Multi-currency without currency on control: only OK if scope is
                # explicitly something other than a combined fake total — block.
                err, _filters = _resolve_declared_total_selection(
                    control, transactions, all_controls=controls_ctx, control_type=control_type
                )
                if err or _control_scope_token(control) == CONTROL_SCOPE_BATCH:
                    return ReconciliationGateResult(
                        gate_id=gate_id,
                        control_type=control_type,
                        control_id=cid,
                        scope_key="BATCH",
                        currency=None,
                        declared_amount=declared,
                        computed_amount=None,
                        difference=None,
                        status=GATE_BLOCKED,
                        reason="MULTI_CURRENCY_BATCH_TOTAL_REQUIRES_CURRENCY_SCOPE",
                    )
        err, filters = _resolve_declared_total_selection(
            control, transactions, all_controls=controls_ctx, control_type=control_type
        )
        if err or filters is None:
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=None,
                currency=None if currency is None else str(currency),
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason=err or "DECLARED_TOTAL_SCOPE_NOT_DETERMINISTIC",
            )
        computed = sum_transaction_totals(transactions, **filters)  # type: ignore[arg-type]
        inv = filters.get("invoice_number")
        card = filters.get("card_or_account_id")
        if inv:
            scope_key = f"INVOICE:{inv}"
        elif card:
            scope_key = f"CARD:{card}"
        elif filters.get("currency"):
            scope_key = f"CURRENCY:{_currency_key(str(filters['currency']))}"
        else:
            scope_key = f"SCOPE:{_control_scope_token(control)}"
    elif control_type == CONTROL_TYPE_CURRENCY_TOTAL:
        if currency is None:
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=None,
                currency=None,
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason="CURRENCY_TOTAL_MISSING_CURRENCY",
            )
        computed = sum_transaction_totals(transactions, currency=str(currency))
        scope_key = f"CURRENCY:{_currency_key(str(currency))}"
    elif control_type == CONTROL_TYPE_CARD_TOTAL:
        card = _norm_scope(
            None
            if _control_attr(control, "scope_card_or_account_id") is None
            else str(_control_attr(control, "scope_card_or_account_id"))
        )
        if card is None:
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=None,
                currency=None if currency is None else str(currency),
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason="CARD_TOTAL_MISSING_SCOPE_CARD",
            )
        computed = sum_transaction_totals(
            transactions,
            currency=None if currency is None else str(currency),
            card_or_account_id=card,
        )
        scope_key = f"CARD:{card}"
    elif control_type == CONTROL_TYPE_UNIT_SUBTOTAL:
        unit = _norm_scope(
            None
            if _control_attr(control, "scope_unit_number_snapshot") is None
            else str(_control_attr(control, "scope_unit_number_snapshot"))
        )
        if unit is None:
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=None,
                currency=None if currency is None else str(currency),
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason="UNIT_SUBTOTAL_MISSING_SCOPE_UNIT",
            )
        computed = sum_transaction_totals(
            transactions,
            currency=None if currency is None else str(currency),
            unit_number=unit,
        )
        scope_key = f"UNIT:{unit}"
    elif control_type == CONTROL_TYPE_PRODUCT_SUBTOTAL:
        if _control_scope_token(control) not in {
            CONTROL_SCOPE_PRODUCT,
            CONTROL_SCOPE_BATCH,
        } and _control_scope_token(control) != CONTROL_SCOPE_UNKNOWN:
            # Allow PRODUCT scope or explicit product key with PRODUCT scope preference.
            pass
        product = _norm_scope(
            None
            if _control_attr(control, "scope_product_raw") is None
            else str(_control_attr(control, "scope_product_raw"))
        )
        if product is None:
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=None,
                currency=None if currency is None else str(currency),
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason="PRODUCT_SCOPE_MISSING",
            )
        computed = sum_transaction_totals(
            transactions,
            currency=None if currency is None else str(currency),
            product=product,
        )
        scope_key = f"PRODUCT:{product}"
    elif control_type == CONTROL_TYPE_GROUP_SUBTOTAL:
        # GROUP must be explicit. Never fall back to unit/product/batch alone.
        if _control_scope_token(control) != CONTROL_SCOPE_GROUP:
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=None,
                currency=None if currency is None else str(currency),
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason="GROUP_SUBTOTAL_REQUIRES_CONTROL_SCOPE_GROUP",
            )
        group_key = _norm_scope(
            None
            if _control_attr(control, "provider_control_identity") is None
            else str(_control_attr(control, "provider_control_identity"))
        )
        if not group_key:
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=None,
                currency=None if currency is None else str(currency),
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason="GROUP_KEY_MISSING",
            )
        if not _txns_have_any_group_identity(transactions):
            return ReconciliationGateResult(
                gate_id=gate_id,
                control_type=control_type,
                control_id=cid,
                scope_key=f"GROUP:{group_key}",
                currency=None if currency is None else str(currency),
                declared_amount=declared,
                computed_amount=None,
                difference=None,
                status=GATE_BLOCKED,
                reason="GROUP_MEMBERSHIP_NOT_DETERMINISTIC",
            )
        computed = sum_transaction_totals(
            transactions,
            currency=None if currency is None else str(currency),
            group_key=group_key,
        )
        scope_key = f"GROUP:{group_key}"
    elif control_type == CONTROL_TYPE_DISCOUNT_CONTROL:
        total = ZERO
        want_ccy = None if currency is None else _currency_key(str(currency))
        for txn in transactions:
            ccy = _txn_attr(txn, "currency")
            amount = _txn_attr(txn, "provider_discount_amount")
            if want_ccy is not None and _currency_key(None if ccy is None else str(ccy)) != want_ccy:
                continue
            if amount is None:
                continue
            total += _money(amount)
        computed = quantize_money(total)
        scope_key = "DISCOUNT"
    elif control_type == CONTROL_TYPE_TAX_CONTROL:
        tax_field = _infer_tax_field(control)
        assert tax_field is not None
        computed = sum_transaction_tax_field(
            transactions,
            field_name=tax_field,
            currency=None if currency is None else str(currency),
        )
        scope_key = f"TAX:{tax_field}"
    else:
        return ReconciliationGateResult(
            gate_id=gate_id,
            control_type=control_type,
            control_id=cid,
            scope_key=None,
            currency=None if currency is None else str(currency),
            declared_amount=declared,
            computed_amount=None,
            difference=None,
            status=GATE_BLOCKED,
            reason="UNSUPPORTED_CONTROL_TYPE_FOR_RECONCILIATION",
        )

    difference = quantize_money(computed - declared)
    if difference == ZERO:
        return ReconciliationGateResult(
            gate_id=gate_id,
            control_type=control_type,
            control_id=cid,
            scope_key=scope_key,
            currency=None if currency is None else str(currency),
            declared_amount=declared,
            computed_amount=computed,
            difference=difference,
            status=GATE_PASS,
            reason=None,
        )

    # Nonzero difference always fails until a proven provider rounding policy exists.
    # Provider VARIANCE rows are recorded separately as evidence; they do not mask this.
    return ReconciliationGateResult(
        gate_id=gate_id,
        control_type=control_type,
        control_id=cid,
        scope_key=scope_key,
        currency=None if currency is None else str(currency),
        declared_amount=declared,
        computed_amount=computed,
        difference=difference,
        status=GATE_FAIL,
        reason="AMOUNT_MISMATCH",
    )


def _unresolved_financial_transaction_blockers(
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
) -> list[str]:
    """Unresolved money-bearing transaction rows must prevent PASS."""
    blockers: list[str] = []
    for txn in transactions:
        tid = _txn_attr(txn, "id")
        amount = _txn_attr(txn, "total_amount")
        event = _norm_scope(
            None
            if _txn_attr(txn, "provider_event_type") is None
            else str(_txn_attr(txn, "provider_event_type"))
        )
        role = _norm_scope(
            None
            if _txn_attr(txn, "reviewed_row_role") is None
            else str(_txn_attr(txn, "reviewed_row_role"))
        ) or _norm_scope(
            None
            if _txn_attr(txn, "parsed_row_role") is None
            else str(_txn_attr(txn, "parsed_row_role"))
        )
        if amount is not None and quantize_money(amount) != ZERO:
            if event in {PROVIDER_EVENT_UNKNOWN, PROVIDER_EVENT_OTHER, None}:
                blockers.append(
                    f"UNRESOLVED_FINANCIAL_TRANSACTION_EVENT:id={tid}:event={event or 'MISSING'}"
                )
            if role and role.upper() not in {"TRANSACTION", "PURCHASE"}:
                # Control-like role left on a money row.
                if role.upper() in {"UNKNOWN", "OTHER", "CONTROL", ""}:
                    blockers.append(
                        f"UNRESOLVED_FINANCIAL_TRANSACTION_ROW_ROLE:id={tid}:role={role}"
                    )
        requires = _txn_attr(txn, "requires_review")
        if requires is True:
            blockers.append(f"TRANSACTION_STILL_REQUIRES_REVIEW:id={tid}")
    return blockers


def reconcile_transactions_and_controls(
    *,
    tenant_id: int,
    batch_id: int,
    provider_code: str,
    transactions: Sequence[FuelTransaction | Mapping[str, Any]],
    controls: Sequence[FuelSourceControl | Mapping[str, Any]],
) -> ReconciliationReport:
    """Pure reconciliation. No DB writes. Decimal arithmetic only."""
    blockers: list[str] = []
    gates: list[ReconciliationGateResult] = []

    # Structural: same source row cannot be both txn and control.
    try:
        assert_no_source_row_double_count(
            (
                t.get("source_row_order") if isinstance(t, Mapping) else t.source_row_order
                for t in transactions
            ),
            (
                c.get("source_row_order") if isinstance(c, Mapping) else c.source_row_order
                for c in controls
            ),
        )
    except Exception as exc:  # FuelControlRowError
        blockers.append(str(exc))

    missing_amounts = []
    for txn in transactions:
        amount = txn.get("total_amount") if isinstance(txn, Mapping) else txn.total_amount
        tid = txn.get("id") if isinstance(txn, Mapping) else getattr(txn, "id", None)
        if amount is None:
            missing_amounts.append(tid)
    if missing_amounts:
        blockers.append(
            f"TRANSACTION_TOTAL_AMOUNT_MISSING:ids={missing_amounts}"
        )

    amount_controls = [
        c
        for c in controls
        if str(_control_attr(c, "control_type") or "") != CONTROL_TYPE_VARIANCE
    ]
    variance_controls = [
        c
        for c in controls
        if str(_control_attr(c, "control_type") or "") == CONTROL_TYPE_VARIANCE
    ]

    blockers.extend(_unresolved_financial_transaction_blockers(transactions))

    if not controls:
        blockers.append("NO_PROVIDER_CONTROLS")
    elif not any(
        str(_control_attr(c, "control_type") or "") in AMOUNT_CONTROL_TYPES
        or str(_control_attr(c, "control_type") or "") == CONTROL_TYPE_TAX_CONTROL
        for c in controls
    ):
        if not any(
            str(_control_attr(c, "control_type") or "") in AMOUNT_CONTROL_TYPES
            for c in controls
        ):
            blockers.append("NO_RECONCILABLE_AMOUNT_CONTROLS")

    for control in amount_controls:
        gates.append(
            evaluate_control_gate(
                control,
                transactions,
                all_controls=controls,
            )
        )

    # Provider VARIANCE rows: preserve as evidence-only gates (never force PASS).
    for ctrl in variance_controls:
        gates.append(
            evaluate_control_gate(
                ctrl,
                transactions,
                all_controls=controls,
            )
        )

    currencies = sorted(
        {
            _currency_key(
                None
                if _txn_attr(t, "currency") is None
                else str(_txn_attr(t, "currency"))
            )
            for t in transactions
            if _txn_attr(t, "currency")
        }
    )

    validated: dict[str, str] = {}
    provider_declared: dict[str, str] = {}
    for ccy in currencies:
        computed = sum_transaction_totals(
            transactions, currency=ccy if ccy != "_NONE_" else None
        )
        validated[ccy] = decimal_json(computed) or "0.0000"
    for control in controls:
        ctype = str(_control_attr(control, "control_type") or "")
        if ctype not in BATCH_LEVEL_CONTROL_TYPES | {CONTROL_TYPE_CURRENCY_TOTAL}:
            continue
        ccy = _control_attr(control, "currency")
        declared = _control_attr(control, "declared_amount")
        if declared is None:
            continue
        key = _currency_key(None if ccy is None else str(ccy))
        provider_declared[key] = decimal_json(quantize_money(declared)) or "0.0000"

    unexplained = [
        g.to_dict()
        for g in gates
        if g.status == GATE_FAIL and g.reason in {"AMOUNT_MISMATCH", "UNEXPLAINED_VARIANCE"}
    ]

    for g in gates:
        if g.status == GATE_BLOCKED and g.reason:
            blockers.append(f"{g.reason}:control_id={g.control_id}")

    has_fail = any(g.status == GATE_FAIL for g in gates)
    has_blocked_gate = any(g.status == GATE_BLOCKED for g in gates)

    if blockers or has_blocked_gate:
        outcome = OUTCOME_BLOCKED
    elif has_fail or unexplained:
        outcome = OUTCOME_RECONCILIATION_FAILED
    else:
        # SKIPPED variance evidence alone does not count as a passing money gate.
        if transactions and not any(g.status == GATE_PASS for g in gates):
            outcome = OUTCOME_BLOCKED
            blockers.append("NO_PASSING_CONTROL_GATES")
        else:
            outcome = OUTCOME_RECONCILED

    return ReconciliationReport(
        outcome=outcome,
        batch_id=batch_id,
        tenant_id=tenant_id,
        provider_code=provider_code,
        transaction_count=len(transactions),
        control_count=len(controls),
        gates=gates,
        unexplained_variances=unexplained,
        blockers=blockers,
        currencies=currencies,
        validated_totals_by_currency=validated,
        provider_totals_by_currency=provider_declared,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor_id(actor: Any) -> str:
    return str(
        getattr(actor, "user_id", None)
        or getattr(actor, "id", None)
        or getattr(actor, "email", None)
        or "unknown"
    )


async def get_batch(
    db: AsyncSession, *, tenant_id: int, batch_id: int
) -> FuelSourceBatch | None:
    return await db.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.id == batch_id,
        )
    )


async def reconcile_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch: FuelSourceBatch,
    actor: Any,
) -> dict[str, Any]:
    """Run Segment 9 reconciliation and persist status + report on the batch.

    Does NOT finalize, post, or resolve financial responsibility (Segment 10+).
    """
    if batch.tenant_id != tenant_id:
        raise FuelReconciliationError("TENANT_MISMATCH", "Batch not in tenant", http_status=404)

    if batch.status not in {
        BATCH_STATUS_READY_FOR_RECONCILIATION,
        BATCH_STATUS_RECONCILIATION_FAILED,
        BATCH_STATUS_BLOCKED,
        BATCH_STATUS_RECONCILED,
    }:
        raise FuelReconciliationError(
            "BATCH_NOT_READY",
            f"Batch status {batch.status!r} is not eligible for reconciliation; "
            f"expected {BATCH_STATUS_READY_FOR_RECONCILIATION}",
            http_status=409,
        )

    txn_rows = list(
        (
            await db.scalars(
                select(FuelTransaction).where(
                    FuelTransaction.tenant_id == tenant_id,
                    FuelTransaction.batch_id == batch.id,
                )
            )
        ).all()
    )
    ctrl_rows = list(
        (
            await db.scalars(
                select(FuelSourceControl).where(
                    FuelSourceControl.tenant_id == tenant_id,
                    FuelSourceControl.batch_id == batch.id,
                )
            )
        ).all()
    )

    # Review gate: rows must be confirmed before money gates run.
    unconfirmed = [
        t.id for t in txn_rows if t.review_status != ROW_REVIEW_CONFIRMED
    ] + [c.id for c in ctrl_rows if c.review_status != ROW_REVIEW_CONFIRMED]
    if unconfirmed:
        raise FuelReconciliationError(
            "ROWS_UNCONFIRMED",
            f"Cannot reconcile: {len(unconfirmed)} row(s) not CONFIRMED in source review",
            http_status=409,
        )

    report = reconcile_transactions_and_controls(
        tenant_id=tenant_id,
        batch_id=batch.id,
        provider_code=batch.provider_code,
        transactions=txn_rows,
        controls=ctrl_rows,
    )

    # Per-row gate visibility (existing column; no migration).
    gate_by_outcome = GATE_PASS if report.outcome == OUTCOME_RECONCILED else (
        GATE_BLOCKED if report.outcome == OUTCOME_BLOCKED else GATE_FAIL
    )
    for txn in txn_rows:
        txn.gate_status = gate_by_outcome

    if report.outcome == OUTCOME_RECONCILED:
        batch.status = BATCH_STATUS_RECONCILED
    elif report.outcome == OUTCOME_BLOCKED:
        batch.status = BATCH_STATUS_BLOCKED
    else:
        batch.status = BATCH_STATUS_RECONCILIATION_FAILED

    summary = dict(batch.problem_summary_json or {})
    summary["reconciliation"] = report.to_dict()
    summary["reconciliation"]["reconciled_at"] = _utcnow().isoformat()
    summary["reconciliation"]["reconciled_by"] = _actor_id(actor)
    batch.problem_summary_json = summary
    batch.updated_by = _actor_id(actor)

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        module=MODULE,
        entity_type="fuel_source_batch",
        entity_id=batch.id,
        action="fuel.reconciliation.run",
        source="ui",
        actor_type="user",
        actor_user_id=int(getattr(actor, "user_id", 0) or 0) or None,
        context_json={
            "outcome": report.outcome,
            "status": batch.status,
            "gate_count": len(report.gates),
            "fail_count": sum(1 for g in report.gates if g.status == GATE_FAIL),
            "blocker_count": len(report.blockers),
            "finalization_implemented": False,
            "financial_responsibility_implemented": False,
            "ai_authority": False,
        },
        visibility="finance_sensitive",
    )
    await db.flush()

    out = report.to_dict()
    out["status"] = batch.status
    out["reconciled_at"] = summary["reconciliation"]["reconciled_at"]
    out["reconciled_by"] = summary["reconciliation"]["reconciled_by"]
    return out


def raise_http(exc: Exception) -> None:
    if isinstance(exc, FuelReconciliationError):
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "detail": exc.message},
        ) from exc
    if isinstance(exc, FuelFloatForbidden):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "FLOAT_FORBIDDEN", "detail": str(exc)},
        ) from exc
    raise exc
