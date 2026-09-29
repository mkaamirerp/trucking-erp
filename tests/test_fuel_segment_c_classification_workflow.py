"""Segment C: human classification workflow (no AI)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.fuel import FuelProviderCategoryMapping, FuelTransaction
from app.services.fuel_bvd_canonical_projection import SECTION_EXPRESS
from app.services.fuel_charge_categories import (
    CATEGORY_OTHER,
    CATEGORY_LUMPER,
    CATEGORY_TOLL,
    CATEGORY_UNMAPPED,
    CLASSIFICATION_SOURCE_MANUAL,
    CLASSIFICATION_SOURCE_TENANT_MAPPING,
    CLASSIFICATION_STATUS_CONFIRMED,
    CLASSIFICATION_STATUS_UNMAPPED,
)
from app.services.fuel_classification_persistence import (
    apply_classification_result,
    classify_transaction_row,
    is_human_confirmed_classification,
)
from app.services.fuel_classification_workflow import (
    apply_manual_classification,
    build_unresolved_reason_groups,
    classification_summary_counts,
    classify_future_transaction_via_mappings,
    transaction_needs_classification,
)
from app.services.fuel_reason_normalize import normalize_provider_reason_key
from app.services.fuel_transaction_classify import FuelTransactionClassificationResult


def _express_txn(
    *,
    txn_id: int,
    reason: str,
    total: str = "100.00",
    batch_id: int = 1,
) -> FuelTransaction:
    return FuelTransaction(
        id=txn_id,
        tenant_id=53,
        batch_id=batch_id,
        source_row_order=txn_id,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="DATE_ONLY",
        provider_section_raw=SECTION_EXPRESS,
        provider_reason_raw=reason,
        total_amount=Decimal(total),
        provider_raw={},
        classification=CATEGORY_UNMAPPED,
        classification_status=CLASSIFICATION_STATUS_UNMAPPED,
    )


def test_summary_counts() -> None:
    txns = [
        _express_txn(txn_id=1, reason="pay"),
        _express_txn(txn_id=2, reason="lumper fee"),
    ]
    txns[1].classification = CATEGORY_LUMPER
    txns[1].classification_status = CLASSIFICATION_STATUS_CONFIRMED
    txns[1].classification_source = CLASSIFICATION_SOURCE_TENANT_MAPPING
    counts = classification_summary_counts(txns)
    assert counts["needs_review"] == 1
    assert counts["confirmed"] == 1


def test_unresolved_groups_exact_reason_only() -> None:
    txns = [
        _express_txn(txn_id=1, reason="load pay", total="100"),
        _express_txn(txn_id=2, reason="load pay", total="200"),
        _express_txn(txn_id=3, reason="lumper", total="64"),
        _express_txn(txn_id=4, reason="lumper fee", total="50"),
    ]
    groups = build_unresolved_reason_groups(txns)
    by_reason = {g["normalized_reason_key"]: g for g in groups}
    assert by_reason["load pay"]["transaction_count"] == 2
    assert Decimal(by_reason["load pay"]["total_amount"]) == Decimal("300")
    assert "lumper" in by_reason
    assert "lumper fee" in by_reason
    assert by_reason["lumper fee"]["transaction_count"] == 1


@pytest.mark.asyncio
async def test_manual_without_remember_no_mapping() -> None:
    txn = _express_txn(txn_id=5, reason="pay")
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=txn)
    with patch(
        "app.services.fuel_classification_workflow.version_tenant_reason_mapping",
        AsyncMock(),
    ) as ver:
        with patch(
            "app.services.fuel_classification_persistence.apply_classification_result",
            AsyncMock(return_value=True),
        ):
            updated = await apply_manual_classification(
                db,
                tenant_id=53,
                transaction_id=5,
                canonical_category=CATEGORY_OTHER,
                remember_mapping=False,
                apply_matching_in_import=False,
                actor_user_id="u1",
            )
    ver.assert_not_awaited()
    assert len(updated) == 1


@pytest.mark.asyncio
async def test_bulk_apply_same_normalized_reason_only() -> None:
    txns = [
        _express_txn(txn_id=1, reason="lumper fee", total="10"),
        _express_txn(txn_id=2, reason=" Lumper   Fee ", total="20"),
        _express_txn(txn_id=3, reason="lumper", total="30"),
    ]
    db = AsyncMock()

    async def _scalar(_q):
        return txns[0]

    async def _execute(_q):
        result = MagicMock()
        result.scalars.return_value.all.return_value = txns
        return result

    db.scalar = _scalar
    db.execute = _execute
    with patch(
        "app.services.fuel_classification_workflow.version_tenant_reason_mapping",
        AsyncMock(return_value=MagicMock(id=99)),
    ):
        with patch(
            "app.services.fuel_classification_persistence.apply_classification_result",
            AsyncMock(return_value=True),
        ) as apply_mock:
            updated = await apply_manual_classification(
                db,
                tenant_id=53,
                transaction_id=1,
                canonical_category=CATEGORY_LUMPER,
                remember_mapping=True,
                apply_matching_in_import=True,
                actor_user_id="u1",
            )
    assert len(updated) == 2
    assert apply_mock.await_count == 2


@pytest.mark.asyncio
async def test_human_sticky_skips_auto_reclassify() -> None:
    txn = _express_txn(txn_id=6, reason="pay")
    txn.classification = CATEGORY_OTHER
    txn.classification_status = CLASSIFICATION_STATUS_CONFIRMED
    txn.classification_source = CLASSIFICATION_SOURCE_MANUAL
    db = MagicMock()
    out = await classify_transaction_row(db, txn=txn, tenant_reason_mappings={}, respect_human_lock=True)
    assert out is None
    assert txn.classification == CATEGORY_OTHER


def test_future_lumper_fee_uses_mapping_pay_stays_unmapped() -> None:
    from app.services.fuel_transaction_classify import classify_fuel_transaction

    mappings = {("BVD", SECTION_EXPRESS, "lumper fee"): (CATEGORY_LUMPER, 1)}
    r1 = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="lumper fee",
        tenant_reason_mappings=mappings,
    )
    r2 = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="pay",
        tenant_reason_mappings=mappings,
    )
    assert r1.classification == CATEGORY_LUMPER
    assert r1.classification_source == CLASSIFICATION_SOURCE_TENANT_MAPPING
    assert r2.classification == CATEGORY_UNMAPPED


def test_normalize_lumper_fee_not_lumper() -> None:
    assert normalize_provider_reason_key(" Lumper   Fee ") == "lumper fee"
    assert normalize_provider_reason_key("lumper") != "lumper fee"


@pytest.mark.asyncio
async def test_mapping_version_preserves_history() -> None:
    from app.services.fuel_classification_persistence import version_tenant_reason_mapping

    active = FuelProviderCategoryMapping(
        id=1,
        tenant_id=53,
        provider_code="BVD",
        provider_section=SECTION_EXPRESS,
        normalized_reason_key="toll pay",
        canonical_category_code=CATEGORY_TOLL,
        mapping_source="TENANT_MAPPING",
        active=True,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=active)
    db.flush = AsyncMock()
    db.add = MagicMock()
    row = await version_tenant_reason_mapping(
        db,
        tenant_id=53,
        provider_code="BVD",
        provider_section=SECTION_EXPRESS,
        normalized_reason_key="toll pay",
        canonical_category_code=CATEGORY_OTHER,
        raw_example="toll pay",
        approved_by="u",
    )
    assert active.active is False
    assert row.canonical_category_code == CATEGORY_OTHER
    db.add.assert_called_once()


def test_no_openai_in_segment_c_modules() -> None:
    import importlib
    from pathlib import Path

    for name in (
        "app.services.fuel_classification_workflow",
    ):
        mod = importlib.import_module(name)
        text = Path(mod.__file__).read_text(encoding="utf-8").lower()
        assert "openai" not in text
