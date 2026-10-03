"""Post-wall canonical processed Fuel read model (Phase 2).

Authoritative list/detail for processed Fuel history. Does not mutate Process,
staging, or provider-native evidence.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelSourceBatch, FuelSourceControl, FuelTransaction
from app.schemas.fuel import fuel_transaction_to_operational_out
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED
from app.services.fuel_controls import (
    CONTROL_TYPE_CARD_TOTAL,
    CONTROL_TYPE_CURRENCY_TOTAL,
    CONTROL_TYPE_INVOICE_TOTAL,
    CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
    CONTROL_TYPE_STATEMENT_TOTAL,
)

# Invoice/statement-level controls outrank per-card subtotals (Nationwide USD billing total).
_PROVIDER_CONTROL_TYPES: tuple[str, ...] = (
    CONTROL_TYPE_CURRENCY_TOTAL,
    CONTROL_TYPE_INVOICE_TOTAL,
    CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
    CONTROL_TYPE_STATEMENT_TOTAL,
    CONTROL_TYPE_CARD_TOTAL,
)


def _format_decimal(amount: Decimal | None) -> str | None:
    if amount is None:
        return None
    return format(amount, "f")


def _iso_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


# Pre-canonical persisted rows only (BVD CUR tokens). Not the TruckERP currency model.
# Provider normalization happens at projection time (classify_currency / provider profiles).
_LEGACY_READ_CURRENCY_ALIASES: Final[dict[str, str]] = {
    "US": "USD",
    "CN": "CAD",
}


def _legacy_read_currency_raw_compat(raw: str | None) -> str | None:
    """Map legacy source tokens when canonical ``currency`` was not stored on old rows."""
    cur = (raw or "").strip().upper()
    if not cur:
        return None
    return _LEGACY_READ_CURRENCY_ALIASES.get(cur, cur)


def _fuel_transaction_currency_key(row: FuelTransaction) -> str | None:
    """Group key: canonical ISO on ``FuelTransaction.currency``; raw compat fallback only."""
    canonical = (row.currency or "").strip()
    if canonical:
        return canonical.upper()
    return _legacy_read_currency_raw_compat(row.currency_raw)


def _fuel_control_currency_key(ctrl: FuelSourceControl) -> str | None:
    canonical = (ctrl.currency or "").strip()
    if canonical:
        return canonical.upper()
    return _legacy_read_currency_raw_compat(ctrl.currency_raw)


def _money_amounts_by_currency(rows: Sequence[FuelTransaction]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        cur = _fuel_transaction_currency_key(row)
        if not cur:
            continue
        amt = row.total_amount
        if amt is None:
            continue
        totals[cur] += amt
    return dict(totals)


def _discount_rollup_by_currency(rows: Sequence[FuelTransaction]) -> dict[str, Decimal | None]:
    """Per-currency discount sum when every line is known; None if any line is unknown."""
    sums: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unknown: set[str] = set()
    for row in rows:
        cur = _fuel_transaction_currency_key(row)
        if not cur:
            continue
        amt = row.provider_discount_amount
        if amt is None:
            unknown.add(cur)
            continue
        if cur not in unknown:
            sums[cur] += amt
    result: dict[str, Decimal | None] = {}
    for cur in set(sums) | unknown:
        if cur in unknown:
            result[cur] = None
        else:
            result[cur] = sums[cur]
    return result


def _currency_financial_summaries_from_transactions(
    transactions: Sequence[FuelTransaction],
) -> list[dict[str, Any]]:
    txn_totals = _money_amounts_by_currency(transactions)
    discount_rollups = _discount_rollup_by_currency(transactions)
    return [
        {
            "currency": cur,
            "total_amount": _format_decimal(txn_totals[cur]) or "0",
            "discount_amount": (
                _format_decimal(discount_rollups[cur])
                if discount_rollups.get(cur) is not None
                else None
            ),
        }
        for cur in sorted(txn_totals.keys())
    ]


def _provider_control_by_currency(controls: Sequence[FuelSourceControl]) -> dict[str, Decimal]:
    ranked: dict[str, tuple[int, Decimal]] = {}
    priority = {t: i for i, t in enumerate(_PROVIDER_CONTROL_TYPES)}
    for ctrl in controls:
        cur = _fuel_control_currency_key(ctrl)
        if not cur:
            continue
        if ctrl.control_type not in priority:
            continue
        amt = ctrl.declared_amount
        if amt is None:
            continue
        rank = priority[ctrl.control_type]
        prev = ranked.get(cur)
        if prev is None or rank < prev[0]:
            ranked[cur] = (rank, amt)
    return {cur: amt for cur, (_rank, amt) in ranked.items()}


def _distinct_purchase_cards(transactions: Sequence[FuelTransaction]) -> list[str]:
    seen: set[str] = set()
    cards: list[str] = []
    for txn in transactions:
        card = (txn.card_or_account_id or "").strip()
        if not card or card in seen:
            continue
        seen.add(card)
        cards.append(card)
    return sorted(cards)


def _summary_from_batch(
    batch: FuelSourceBatch,
    *,
    transactions: Sequence[FuelTransaction],
    controls: Sequence[FuelSourceControl],
) -> dict[str, Any]:
    txn_totals = _money_amounts_by_currency(transactions)
    control_totals = _provider_control_by_currency(controls)
    currency_totals = [
        {"currency": cur, "amount": _format_decimal(amt) or "0"}
        for cur, amt in sorted(txn_totals.items())
    ]
    currency_financial_summaries = _currency_financial_summaries_from_transactions(transactions)
    provider_control_totals = [
        {"currency": cur, "amount": _format_decimal(amt) or "0"}
        for cur, amt in sorted(control_totals.items())
    ]
    purchase_cards = _distinct_purchase_cards(transactions)
    single_currency = list(txn_totals.keys()) if len(txn_totals) == 1 else []

    return {
        "batch_id": batch.id,
        "provider_code": batch.provider_code,
        "source_import_ref": batch.source_import_ref,
        "source_storage_ref": batch.source_storage_ref,
        "account_reference": batch.account_reference,
        "invoice_number": batch.invoice_number or "—",
        "period_start": _iso_date(batch.statement_start),
        "period_end": _iso_date(batch.statement_end),
        "due_date": _iso_date(batch.due_date),
        "finalized_at": _iso_datetime(batch.finalized_at),
        "batch_status": batch.status,
        "transaction_count": len(transactions),
        "control_count": len(controls),
        "currency_totals": currency_totals,
        "currency_financial_summaries": currency_financial_summaries,
        "provider_control_totals": provider_control_totals,
        # Legacy compatibility fields (CAD/USD buckets). Primary UI uses currency_financial_summaries.
        "cad_transaction_total": _format_decimal(txn_totals.get("CAD")),
        "usd_transaction_total": _format_decimal(txn_totals.get("USD")),
        "usd_provider_control": _format_decimal(control_totals.get("USD")),
        "purchase_card_count": len(purchase_cards),
        "purchase_card_numbers": purchase_cards,
        "total_amount": _format_decimal(txn_totals[single_currency[0]]) if single_currency else "",
        "currency": single_currency[0] if single_currency else None,
        "read_only": True,
        "review_status": "SOURCE_REVIEWED",
    }


async def _load_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
) -> FuelSourceBatch:
    batch = await db.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.id == batch_id,
            FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            FuelSourceBatch.finalized_at.isnot(None),
        )
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processed Fuel batch not found")
    return batch


async def _load_transactions(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
) -> list[FuelTransaction]:
    result = await db.scalars(
        select(FuelTransaction)
        .where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch_id,
        )
        .order_by(FuelTransaction.source_row_order.asc(), FuelTransaction.id.asc())
    )
    return list(result.all())


async def _load_controls(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
) -> list[FuelSourceControl]:
    result = await db.scalars(
        select(FuelSourceControl)
        .where(
            FuelSourceControl.tenant_id == tenant_id,
            FuelSourceControl.batch_id == batch_id,
        )
        .order_by(FuelSourceControl.source_row_order.asc().nulls_last(), FuelSourceControl.id.asc())
    )
    return list(result.all())


async def list_processed_fuel(
    db: AsyncSession,
    *,
    tenant_id: int,
    provider_code: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """FINALIZED canonical batches for tenant, newest first."""
    stmt = (
        select(FuelSourceBatch)
        .where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            FuelSourceBatch.finalized_at.isnot(None),
        )
        .order_by(FuelSourceBatch.finalized_at.desc(), FuelSourceBatch.id.desc())
    )
    if provider_code:
        stmt = stmt.where(FuelSourceBatch.provider_code == provider_code.upper())
    if limit is not None:
        stmt = stmt.limit(limit)

    batches = list((await db.scalars(stmt)).all())
    if not batches:
        return []

    batch_ids = [b.id for b in batches]
    txn_rows = list(
        (
            await db.scalars(
                select(FuelTransaction).where(
                    FuelTransaction.tenant_id == tenant_id,
                    FuelTransaction.batch_id.in_(batch_ids),
                )
            )
        ).all()
    )
    ctrl_rows = list(
        (
            await db.scalars(
                select(FuelSourceControl).where(
                    FuelSourceControl.tenant_id == tenant_id,
                    FuelSourceControl.batch_id.in_(batch_ids),
                )
            )
        ).all()
    )

    txns_by_batch: dict[int, list[FuelTransaction]] = defaultdict(list)
    for txn in txn_rows:
        txns_by_batch[txn.batch_id].append(txn)
    ctrls_by_batch: dict[int, list[FuelSourceControl]] = defaultdict(list)
    for ctrl in ctrl_rows:
        ctrls_by_batch[ctrl.batch_id].append(ctrl)

    return [
        _summary_from_batch(
            batch,
            transactions=txns_by_batch.get(batch.id, []),
            controls=ctrls_by_batch.get(batch.id, []),
        )
        for batch in batches
    ]


async def get_processed_fuel_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
) -> dict[str, Any]:
    batch = await _load_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    transactions = await _load_transactions(db, tenant_id=tenant_id, batch_id=batch_id)
    controls = await _load_controls(db, tenant_id=tenant_id, batch_id=batch_id)
    summary = _summary_from_batch(batch, transactions=transactions, controls=controls)
    summary["canonical_transactions"] = transactions
    summary["canonical_controls"] = controls
    summary["operational_transactions"] = [
        fuel_transaction_to_operational_out(t) for t in transactions
    ]
    return summary
