"""Segment C: human classification workflow (grouping, bulk apply, audit views)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelSourceBatch, FuelTransaction, FuelTransactionClassificationEvent
from app.services.fuel_charge_categories import CATEGORY_UNMAPPED, CLASSIFICATION_STATUS_UNMAPPED
from app.services.fuel_classification_persistence import (
    FuelClassificationError,
    is_human_confirmed_classification,
    list_canonical_transactions_for_import,
    set_transaction_classification_manual,
    version_tenant_reason_mapping,
)
from app.services.fuel_reason_normalize import normalize_provider_reason_key
from app.services.fuel_transaction_classify import FuelTransactionClassificationResult
from app.services.fuel_charge_categories import (
    CLASSIFICATION_SOURCE_MANUAL,
    CLASSIFICATION_SOURCE_TENANT_MAPPING,
    CLASSIFICATION_STATUS_CONFIRMED,
)


def transaction_needs_classification(txn: FuelTransaction) -> bool:
    if is_human_confirmed_classification(txn):
        return False
    if txn.classification_status == CLASSIFICATION_STATUS_UNMAPPED:
        return True
    if txn.classification in (None, "", CATEGORY_UNMAPPED):
        return True
    return False


def classification_summary_counts(transactions: list[FuelTransaction]) -> dict[str, int]:
    confirmed = 0
    needs_review = 0
    for t in transactions:
        if transaction_needs_classification(t):
            needs_review += 1
        else:
            confirmed += 1
    return {"confirmed": confirmed, "needs_review": needs_review, "total": len(transactions)}


def _reason_group_key(txn: FuelTransaction) -> tuple[str, str, str, str] | None:
    reason_key = normalize_provider_reason_key(txn.provider_reason_raw)
    if not reason_key:
        return None
    section = (txn.provider_section_raw or "").strip()
    provider = (txn.source_vendor or "").strip().upper()
    if not section or not provider:
        return None
    return provider, section, reason_key, txn.provider_reason_raw or reason_key


def build_unresolved_reason_groups(
    transactions: list[FuelTransaction],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str, str], list[FuelTransaction]] = defaultdict(list)
    for txn in transactions:
        if not transaction_needs_classification(txn):
            continue
        key = _reason_group_key(txn)
        if key is None:
            continue
        buckets[key].append(txn)

    groups: list[dict[str, Any]] = []
    for (provider, section, norm_key, sample_raw), txns in sorted(
        buckets.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])
    ):
        total = sum((t.total_amount or Decimal("0") for t in txns), Decimal("0"))
        groups.append(
            {
                "provider_code": provider,
                "provider_section_raw": section,
                "provider_reason_raw": sample_raw,
                "normalized_reason_key": norm_key,
                "transaction_count": len(txns),
                "total_amount": format(total, "f"),
                "transaction_ids": [t.id for t in txns],
                "classification": txns[0].classification or CATEGORY_UNMAPPED,
            }
        )
    return groups


async def _transactions_matching_reason_in_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
    provider_code: str,
    provider_section_raw: str,
    normalized_reason_key: str,
) -> list[FuelTransaction]:
    provider = provider_code.strip().upper()
    section = provider_section_raw.strip()
    result = await db.execute(
        select(FuelTransaction).where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch_id,
        )
    )
    matches: list[FuelTransaction] = []
    for txn in result.scalars().all():
        if (txn.source_vendor or "").strip().upper() != provider:
            continue
        if (txn.provider_section_raw or "").strip() != section:
            continue
        if normalize_provider_reason_key(txn.provider_reason_raw) != normalized_reason_key:
            continue
        matches.append(txn)
    return matches


async def apply_manual_classification(
    db: AsyncSession,
    *,
    tenant_id: int,
    transaction_id: int,
    canonical_category: str,
    remember_mapping: bool,
    apply_matching_in_import: bool,
    actor_user_id: str,
) -> list[FuelTransaction]:
    """Classify one transaction; optionally same exact reason in import; optional remember."""
    seed = await db.scalar(
        select(FuelTransaction).where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.id == transaction_id,
        )
    )
    if seed is None:
        raise FuelClassificationError("TXN_NOT_FOUND", "Fuel transaction not found", http_status=404)

    norm_key = normalize_provider_reason_key(seed.provider_reason_raw)
    section = (seed.provider_section_raw or "").strip()
    if not norm_key or not section:
        if apply_matching_in_import:
            raise FuelClassificationError(
                "REASON_KEY_INSUFFICIENT",
                "Cannot bulk-apply without provider section and reason text",
            )
        targets = [seed]
    elif apply_matching_in_import:
        targets = await _transactions_matching_reason_in_batch(
            db,
            tenant_id=tenant_id,
            batch_id=seed.batch_id,
            provider_code=seed.source_vendor,
            provider_section_raw=section,
            normalized_reason_key=norm_key,
        )
    else:
        targets = [seed]

    mapping_id: int | None = None
    if remember_mapping:
        mapping = await version_tenant_reason_mapping(
            db,
            tenant_id=tenant_id,
            provider_code=seed.source_vendor,
            provider_section=section,
            normalized_reason_key=norm_key,
            canonical_category_code=canonical_category,
            raw_example=seed.provider_reason_raw,
            approved_by=actor_user_id,
        )
        mapping_id = mapping.id

    updated: list[FuelTransaction] = []
    for txn in targets:
        if is_human_confirmed_classification(txn) and txn.id != transaction_id:
            continue
        if is_human_confirmed_classification(txn) and txn.id == transaction_id:
            pass
        source = (
            CLASSIFICATION_SOURCE_TENANT_MAPPING if remember_mapping else CLASSIFICATION_SOURCE_MANUAL
        )
        from app.services.fuel_classification_persistence import apply_classification_result

        money_before = (
            txn.principal_amount,
            txn.provider_fee_amount,
            txn.total_amount,
        )
        result = FuelTransactionClassificationResult(
            classification=canonical_category,
            classification_status=CLASSIFICATION_STATUS_CONFIRMED,
            classification_source=source,
            mapping_id=mapping_id if remember_mapping else None,
        )
        await apply_classification_result(
            db,
            txn=txn,
            result=result,
            actor_user_id=actor_user_id,
            metadata_json={
                "remember_mapping": remember_mapping,
                "apply_matching_in_import": apply_matching_in_import,
                "manual": True,
                "seed_transaction_id": transaction_id,
            },
        )
        if (
            txn.principal_amount,
            txn.provider_fee_amount,
            txn.total_amount,
        ) != money_before:
            raise FuelClassificationError(
                "MONEY_MUTATION_FORBIDDEN",
                "Classification must not alter transaction money fields",
                http_status=500,
            )
        updated.append(txn)
    if not updated:
        raise FuelClassificationError("NO_TARGETS", "No transactions updated (all human-locked?)")
    return updated


async def classify_reason_group_in_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: str,
    provider_section_raw: str,
    provider_reason_raw: str,
    canonical_category: str,
    remember_mapping: bool,
    actor_user_id: str,
) -> list[FuelTransaction]:
    batch = await db.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.source_import_ref == import_id,
        )
    )
    if batch is None:
        raise FuelClassificationError("BATCH_NOT_FOUND", "No canonical batch for import")

    norm_key = normalize_provider_reason_key(provider_reason_raw)
    if not norm_key:
        raise FuelClassificationError("REASON_KEY_INSUFFICIENT", "Provider reason required")

    txns = await _transactions_matching_reason_in_batch(
        db,
        tenant_id=tenant_id,
        batch_id=batch.id,
        provider_code=batch.provider_code,
        provider_section_raw=provider_section_raw,
        normalized_reason_key=norm_key,
    )
    if not txns:
        raise FuelClassificationError("NO_MATCHING_TRANSACTIONS", "No transactions for reason group")

    seed_id = txns[0].id
    return await apply_manual_classification(
        db,
        tenant_id=tenant_id,
        transaction_id=seed_id,
        canonical_category=canonical_category,
        remember_mapping=remember_mapping,
        apply_matching_in_import=True,
        actor_user_id=actor_user_id,
    )


async def get_classification_summary_for_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: str,
) -> dict[str, Any]:
    txns = await list_canonical_transactions_for_import(db, tenant_id=tenant_id, import_id=import_id)
    if not txns:
        raise FuelClassificationError("BATCH_NOT_FOUND", "No canonical batch for import")
    counts = classification_summary_counts(txns)
    return {
        "import_id": import_id,
        **counts,
    }


async def get_unresolved_groups_for_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: str,
) -> list[dict[str, Any]]:
    txns = await list_canonical_transactions_for_import(db, tenant_id=tenant_id, import_id=import_id)
    if not txns:
        raise FuelClassificationError("BATCH_NOT_FOUND", "No canonical batch for import")
    return build_unresolved_reason_groups(txns)


async def list_classification_audit_for_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: str,
    limit: int = 200,
) -> list[dict[str, Any]]:
    batch = await db.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.source_import_ref == import_id,
        )
    )
    if batch is None:
        return []
    result = await db.execute(
        select(FuelTransactionClassificationEvent, FuelTransaction)
        .join(
            FuelTransaction,
            (FuelTransactionClassificationEvent.fuel_transaction_id == FuelTransaction.id)
            & (FuelTransactionClassificationEvent.tenant_id == FuelTransaction.tenant_id),
        )
        .where(
            FuelTransactionClassificationEvent.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch.id,
        )
        .order_by(FuelTransactionClassificationEvent.id.desc())
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    for event, txn in result.all():
        meta = event.metadata_json or {}
        out.append(
            {
                "id": event.id,
                "fuel_transaction_id": event.fuel_transaction_id,
                "provider_reason_raw": txn.provider_reason_raw,
                "previous_category": event.previous_category,
                "proposed_category": event.proposed_category,
                "source": event.source,
                "mapping_id": event.mapping_id,
                "actor_user_id": event.actor_user_id,
                "created_at": event.created_at.isoformat() if event.created_at else None,
                "remember_mapping": meta.get("remember_mapping"),
                "apply_matching_in_import": meta.get("apply_matching_in_import"),
                "previous_state": meta.get("previous_state"),
                "proposed_state": meta.get("proposed_state"),
            }
        )
    return out


async def classify_future_transaction_via_mappings(
    db: AsyncSession,
    *,
    tenant_id: int,
    txn: FuelTransaction,
) -> FuelTransactionClassificationResult:
    """Resolve one transaction using automatic rules only (for future-import proof tests)."""
    from app.services.fuel_classification_persistence import (
        classify_transaction_row,
        load_active_tenant_reason_mappings,
    )

    mappings = await load_active_tenant_reason_mappings(
        db, tenant_id=tenant_id, provider_code=txn.source_vendor
    )
    result = await classify_transaction_row(
        db, txn=txn, tenant_reason_mappings=mappings, respect_human_lock=True
    )
    if result is None:
        from app.services.fuel_transaction_classify import classify_fuel_transaction

        return classify_fuel_transaction(
            tenant_id=tenant_id,
            provider_code=txn.source_vendor,
            provider_section_raw=txn.provider_section_raw,
            product_code_raw=txn.product_code_raw,
            provider_reason_raw=txn.provider_reason_raw,
            tenant_reason_mappings=mappings,
        )
    return result
