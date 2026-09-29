"""Persist fuel transaction classification + append-only audit (Segment B)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import (
    FuelProviderCategoryMapping,
    FuelSourceBatch,
    FuelTransaction,
    FuelTransactionClassificationEvent,
)
from app.services.fuel_charge_categories import (
    CANONICAL_CATEGORY_CODES,
    CATEGORY_UNMAPPED,
    CLASSIFICATION_SOURCE_MANUAL,
    CLASSIFICATION_SOURCE_TENANT_MAPPING,
    CLASSIFICATION_STATUS_CONFIRMED,
    MAPPING_SOURCE_TENANT_MAPPING,
)
from app.services.fuel_reason_normalize import normalize_provider_reason_key
from app.services.fuel_transaction_classify import (
    FuelTransactionClassificationResult,
    classify_fuel_transaction,
)

logger = logging.getLogger(__name__)


class FuelClassificationError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def _txn_classification_state(txn: FuelTransaction) -> dict[str, Any]:
    return {
        "classification": txn.classification,
        "classification_status": txn.classification_status,
        "classification_source": txn.classification_source,
        "classification_mapping_id": txn.classification_mapping_id,
    }


def _result_state(result: FuelTransactionClassificationResult) -> dict[str, Any]:
    return {
        "classification": result.classification,
        "classification_status": result.classification_status,
        "classification_source": result.classification_source,
        "classification_mapping_id": result.mapping_id,
    }


def _states_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left == right


def is_human_confirmed_classification(txn: FuelTransaction) -> bool:
    return (
        txn.classification_source == CLASSIFICATION_SOURCE_MANUAL
        and txn.classification_status == CLASSIFICATION_STATUS_CONFIRMED
        and txn.classification is not None
        and txn.classification != CATEGORY_UNMAPPED
    )


async def load_active_tenant_reason_mappings(
    db: AsyncSession,
    *,
    tenant_id: int,
    provider_code: str,
) -> dict[tuple[str, str, str], tuple[str, int]]:
    provider = provider_code.strip().upper()
    result = await db.execute(
        select(FuelProviderCategoryMapping).where(
            FuelProviderCategoryMapping.tenant_id == tenant_id,
            FuelProviderCategoryMapping.provider_code == provider,
            FuelProviderCategoryMapping.active.is_(True),
        )
    )
    out: dict[tuple[str, str, str], tuple[str, int]] = {}
    for row in result.scalars().all():
        key = (
            row.provider_code.strip().upper(),
            (row.provider_section or "").strip(),
            row.normalized_reason_key,
        )
        out[key] = (row.canonical_category_code, row.id)
    return out


async def _append_classification_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    fuel_transaction_id: int,
    previous_state: dict[str, Any],
    proposed_state: dict[str, Any],
    source: str | None,
    reason_code: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    actor_user_id: str | None = None,
) -> None:
    meta = dict(metadata_json or {})
    meta["previous_state"] = previous_state
    meta["proposed_state"] = proposed_state
    db.add(
        FuelTransactionClassificationEvent(
            tenant_id=tenant_id,
            fuel_transaction_id=fuel_transaction_id,
            previous_category=previous_state.get("classification"),
            proposed_category=proposed_state.get("classification") or CATEGORY_UNMAPPED,
            source=source,
            mapping_id=proposed_state.get("classification_mapping_id"),
            reason_code=reason_code,
            metadata_json=meta,
            actor_user_id=actor_user_id,
        )
    )


async def apply_classification_result(
    db: AsyncSession,
    *,
    txn: FuelTransaction,
    result: FuelTransactionClassificationResult,
    actor_user_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    force_event: bool = False,
) -> bool:
    """Apply classification; append audit only when effective state changes."""
    previous_state = _txn_classification_state(txn)
    proposed_state = _result_state(result)
    if not force_event and _states_equal(previous_state, proposed_state):
        return False

    await _append_classification_event(
        db,
        tenant_id=txn.tenant_id,
        fuel_transaction_id=txn.id,
        previous_state=previous_state,
        proposed_state=proposed_state,
        source=result.classification_source,
        metadata_json=metadata_json,
        actor_user_id=actor_user_id,
    )

    txn.classification = result.classification
    txn.classification_status = result.classification_status
    txn.classification_source = result.classification_source
    txn.classification_mapping_id = result.mapping_id
    return True


async def classify_transaction_row(
    db: AsyncSession,
    *,
    txn: FuelTransaction,
    tenant_reason_mappings: dict[tuple[str, str, str], tuple[str, int]] | None = None,
    actor_user_id: str | None = None,
    respect_human_lock: bool = True,
) -> FuelTransactionClassificationResult | None:
    if respect_human_lock and is_human_confirmed_classification(txn):
        return None
    result = classify_fuel_transaction(
        tenant_id=txn.tenant_id,
        provider_code=txn.source_vendor,
        provider_section_raw=txn.provider_section_raw,
        product_code_raw=txn.product_code_raw,
        provider_reason_raw=txn.provider_reason_raw,
        tenant_reason_mappings=tenant_reason_mappings,
    )
    await apply_classification_result(db, txn=txn, result=result, actor_user_id=actor_user_id)
    return result


async def classify_transactions_for_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    transactions: list[FuelTransaction],
) -> int:
    if not transactions:
        return 0
    provider = transactions[0].source_vendor
    mappings = await load_active_tenant_reason_mappings(
        db, tenant_id=tenant_id, provider_code=provider
    )
    changed = 0
    for txn in transactions:
        if txn.tenant_id != tenant_id:
            continue
        before = _txn_classification_state(txn)
        applied = await classify_transaction_row(
            db, txn=txn, tenant_reason_mappings=mappings, respect_human_lock=True
        )
        if applied is not None and not _states_equal(before, _txn_classification_state(txn)):
            changed += 1
    return changed


async def backfill_classifications_for_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: str,
) -> int:
    batch = await db.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.source_import_ref == import_id,
        )
    )
    if batch is None:
        raise FuelClassificationError("BATCH_NOT_FOUND", "No canonical batch for import")
    result = await db.execute(
        select(FuelTransaction).where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch.id,
        )
    )
    txns = list(result.scalars().all())
    return await classify_transactions_for_batch(db, tenant_id=tenant_id, transactions=txns)


async def best_effort_backfill_classifications_for_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: str,
) -> int:
    """Post-canonical classification in its own transaction; never rolls back money."""
    try:
        changed = await backfill_classifications_for_import(
            db, tenant_id=tenant_id, import_id=import_id
        )
        await db.commit()
        return changed
    except Exception:
        await db.rollback()
        logger.exception(
            "fuel classification post-process failed tenant_id=%s import_id=%s",
            tenant_id,
            import_id,
        )
        return 0


async def list_canonical_transactions_for_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: str,
) -> list[FuelTransaction]:
    batch = await db.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.source_import_ref == import_id,
        )
    )
    if batch is None:
        return []
    result = await db.execute(
        select(FuelTransaction)
        .where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch.id,
        )
        .order_by(FuelTransaction.source_row_order.asc())
    )
    return list(result.scalars().all())


async def version_tenant_reason_mapping(
    db: AsyncSession,
    *,
    tenant_id: int,
    provider_code: str,
    provider_section: str,
    normalized_reason_key: str,
    canonical_category_code: str,
    raw_example: str | None,
    approved_by: str,
) -> FuelProviderCategoryMapping:
    if canonical_category_code not in CANONICAL_CATEGORY_CODES:
        raise FuelClassificationError("INVALID_CATEGORY", f"Unknown category: {canonical_category_code}")
    if canonical_category_code == CATEGORY_UNMAPPED:
        raise FuelClassificationError("INVALID_CATEGORY", "Cannot map to UNMAPPED")

    provider = provider_code.strip().upper()
    section = provider_section.strip()
    now = datetime.now(timezone.utc)

    active = await db.scalar(
        select(FuelProviderCategoryMapping).where(
            FuelProviderCategoryMapping.tenant_id == tenant_id,
            FuelProviderCategoryMapping.provider_code == provider,
            FuelProviderCategoryMapping.provider_section == section,
            FuelProviderCategoryMapping.normalized_reason_key == normalized_reason_key,
            FuelProviderCategoryMapping.active.is_(True),
        )
    )
    if active is not None:
        if active.canonical_category_code == canonical_category_code:
            if raw_example and active.raw_example != raw_example:
                active.raw_example = raw_example
                active.updated_at = now
            return active
        active.active = False
        active.updated_at = now
        await db.flush()

    row = FuelProviderCategoryMapping(
        tenant_id=tenant_id,
        provider_code=provider,
        provider_section=section,
        normalized_reason_key=normalized_reason_key,
        raw_example=raw_example,
        canonical_category_code=canonical_category_code,
        mapping_source=MAPPING_SOURCE_TENANT_MAPPING,
        approved_by=approved_by,
        approved_at=now,
        active=True,
    )
    db.add(row)
    await db.flush()
    return row


async def upsert_tenant_reason_mapping(
    db: AsyncSession,
    *,
    tenant_id: int,
    provider_code: str,
    provider_section: str,
    normalized_reason_key: str,
    canonical_category_code: str,
    raw_example: str | None,
    approved_by: str,
) -> FuelProviderCategoryMapping:
    return await version_tenant_reason_mapping(
        db,
        tenant_id=tenant_id,
        provider_code=provider_code,
        provider_section=provider_section,
        normalized_reason_key=normalized_reason_key,
        canonical_category_code=canonical_category_code,
        raw_example=raw_example,
        approved_by=approved_by,
    )


async def set_transaction_classification_manual(
    db: AsyncSession,
    *,
    tenant_id: int,
    transaction_id: int,
    canonical_category: str,
    remember_mapping: bool,
    actor_user_id: str,
    apply_matching_in_import: bool = False,
) -> FuelTransaction:
    from app.services.fuel_classification_workflow import apply_manual_classification

    if canonical_category not in CANONICAL_CATEGORY_CODES:
        raise FuelClassificationError("INVALID_CATEGORY", f"Unknown category: {canonical_category}")
    if canonical_category == CATEGORY_UNMAPPED:
        raise FuelClassificationError("INVALID_CATEGORY", "Use classification resolver for UNMAPPED")

    try:
        updated = await apply_manual_classification(
            db,
            tenant_id=tenant_id,
            transaction_id=transaction_id,
            canonical_category=canonical_category,
            remember_mapping=remember_mapping,
            apply_matching_in_import=apply_matching_in_import,
            actor_user_id=actor_user_id,
        )
    except FuelClassificationError as exc:
        if exc.code == "TXN_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
        raise
    return updated[0]


def _money_snapshot(txn: FuelTransaction) -> tuple[Any, ...]:
    return (
        txn.principal_amount,
        txn.provider_fee_amount,
        txn.total_amount,
        txn.quantity,
        txn.unit_price,
        txn.tax_amount,
        txn.hst_amount,
        txn.gst_amount,
        txn.pst_amount,
        txn.qst_amount,
        txn.currency,
        txn.currency_raw,
        txn.unit_number_snapshot,
        txn.driver_name_snapshot,
    )


async def count_classification_events_for_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(FuelTransactionClassificationEvent)
        .join(
            FuelTransaction,
            (FuelTransactionClassificationEvent.fuel_transaction_id == FuelTransaction.id)
            & (FuelTransactionClassificationEvent.tenant_id == FuelTransaction.tenant_id),
        )
        .where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch_id,
        )
    )
    return int(count or 0)


def raise_http_from_classification_error(exc: FuelClassificationError) -> None:
    raise HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": exc.message},
    ) from exc
