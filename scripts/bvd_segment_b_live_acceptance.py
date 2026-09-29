#!/usr/bin/env python3
"""Segment B live acceptance on tenant_demo (run inside truckerp-api with secrets)."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.models.fuel import (
    FuelChargeCategory,
    FuelProviderCategoryMapping,
    FuelSourceBatch,
    FuelTransaction,
    FuelTransactionClassificationEvent,
)
from app.services.fuel_bvd_canonical_projection import SECTION_EXPRESS, SECTION_FUEL_CARD
from app.services.fuel_charge_categories import (
    CATEGORY_OTHER,
    CATEGORY_LUMPER,
    CATEGORY_UNMAPPED,
    CLASSIFICATION_SOURCE_MANUAL,
    CLASSIFICATION_SOURCE_PROVIDER_RULE,
    CLASSIFICATION_SOURCE_TENANT_MAPPING,
    CLASSIFICATION_STATUS_CONFIRMED,
    CLASSIFICATION_STATUS_UNMAPPED,
)
from app.services.fuel_classification_persistence import (
    backfill_classifications_for_import,
    set_transaction_classification_manual,
    version_tenant_reason_mapping,
)
from app.services.fuel_reason_normalize import normalize_provider_reason_key

TENANT_ID = 53
INVOICE_838710 = "838710"
INVOICE_972201 = "972201"


def _pg_url() -> str:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        raise RuntimeError("TENANT_DATABASE_URL not set")
    return to_async_pg_url(raw)


async def _import_id_for_invoice(session: AsyncSession, invoice: str) -> str | None:
    batch = await session.scalar(
        select(FuelSourceBatch)
        .where(
            FuelSourceBatch.tenant_id == TENANT_ID,
            FuelSourceBatch.invoice_number == invoice,
            FuelSourceBatch.status == "FINALIZED",
        )
        .order_by(FuelSourceBatch.id.desc())
    )
    return batch.source_import_ref if batch else None


async def _txn_snapshot(session: AsyncSession, batch_id: int) -> dict[str, Any]:
    rows = list(
        (
            await session.execute(
                select(FuelTransaction).where(
                    FuelTransaction.tenant_id == TENANT_ID,
                    FuelTransaction.batch_id == batch_id,
                )
            )
        ).scalars().all()
    )
    total = sum((r.total_amount or Decimal("0") for r in rows), Decimal("0"))
    money_sig = [
        {
            "id": r.id,
            "principal": str(r.principal_amount),
            "fee": str(r.provider_fee_amount),
            "total": str(r.total_amount),
            "qty": str(r.quantity),
            "unit": r.unit_number_snapshot,
            "driver": r.driver_name_snapshot,
        }
        for r in rows
    ]
    breakdown = Counter(
        (
            r.provider_section_raw or "",
            r.classification or "",
            r.classification_status or "",
            r.classification_source or "",
        )
        for r in rows
    )
    return {
        "count": len(rows),
        "sum": str(total),
        "breakdown": [
            {
                "section": k[0],
                "classification": k[1],
                "status": k[2],
                "source": k[3],
                "n": v,
            }
            for k, v in sorted(breakdown.items())
        ],
        "money_sig": money_sig,
    }


async def main() -> int:
    engine = create_async_engine(_pg_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report: dict[str, Any] = {}

    async with factory() as session:
        imp838 = await _import_id_for_invoice(session, INVOICE_838710)
        imp972 = await _import_id_for_invoice(session, INVOICE_972201)
        report["import_ids"] = {"838710": imp838, "972201": imp972}
        if not imp838:
            raise RuntimeError("838710 finalized batch not found")

        batch = await session.scalar(
            select(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == imp838,
            )
        )
        report["batch_id_838710"] = batch.id
        report["money_before"] = await _txn_snapshot(session, batch.id)

        # Clear mappings for clean initial backfill test
        await session.execute(
            text(
                "UPDATE fuel_provider_category_mapping SET active = false "
                "WHERE tenant_id = :tid AND provider_code = 'BVD'"
            ),
            {"tid": TENANT_ID},
        )
        await session.commit()

    async with factory() as session:
        changed = await backfill_classifications_for_import(
            session, tenant_id=TENANT_ID, import_id=imp838
        )
        await session.commit()
        report["initial_backfill_changed"] = changed
        batch_id = report["batch_id_838710"]
        report["after_initial_backfill"] = await _txn_snapshot(session, batch_id)
        events_after_1 = await session.scalar(
            select(func.count())
            .select_from(FuelTransactionClassificationEvent)
            .where(FuelTransactionClassificationEvent.tenant_id == TENANT_ID)
        )
        report["events_after_initial_backfill"] = events_after_1

    async with factory() as session:
        changed2 = await backfill_classifications_for_import(
            session, tenant_id=TENANT_ID, import_id=imp838
        )
        await session.commit()
        report["second_backfill_changed"] = changed2
        events_after_2 = await session.scalar(
            select(func.count())
            .select_from(FuelTransactionClassificationEvent)
            .where(FuelTransactionClassificationEvent.tenant_id == TENANT_ID)
        )
        report["events_after_second_backfill"] = events_after_2

    async with factory() as session:
        await version_tenant_reason_mapping(
            session,
            tenant_id=TENANT_ID,
            provider_code="BVD",
            provider_section=SECTION_EXPRESS,
            normalized_reason_key="lumper fee",
            canonical_category_code=CATEGORY_LUMPER,
            raw_example="lumper fee",
            approved_by="segment_b_acceptance",
        )
        await session.commit()
        changed3 = await backfill_classifications_for_import(
            session, tenant_id=TENANT_ID, import_id=imp838
        )
        await session.commit()
        report["after_lumper_fee_mapping_backfill_changed"] = changed3
        batch_id = report["batch_id_838710"]
        snap = await _txn_snapshot(session, batch_id)
        report["after_lumper_fee_mapping"] = snap
        express = list(
            (
                await session.execute(
                    select(FuelTransaction).where(
                        FuelTransaction.tenant_id == TENANT_ID,
                        FuelTransaction.batch_id == batch_id,
                        FuelTransaction.provider_section_raw == SECTION_EXPRESS,
                    )
                )
            ).scalars().all()
        )
        report["lumper_fee_rows"] = sum(
            1
            for t in express
            if normalize_provider_reason_key(t.provider_reason_raw) == "lumper fee"
            and t.classification == CATEGORY_LUMPER
            and t.classification_source == CLASSIFICATION_SOURCE_TENANT_MAPPING
        )
        report["lumper_only_unmapped"] = all(
            t.classification == CATEGORY_UNMAPPED
            for t in express
            if normalize_provider_reason_key(t.provider_reason_raw) == "lumper"
        )
        report["pay_rows_unmapped"] = all(
            t.classification == CATEGORY_UNMAPPED
            for t in express
            if normalize_provider_reason_key(t.provider_reason_raw) == "pay"
        )

        report["normalization_key_proof"] = {
            "spaced_input": normalize_provider_reason_key(" Lumper   Fee "),
            "matches_mapping_key": normalize_provider_reason_key(" Lumper   Fee ")
            == "lumper fee",
            "lumper_not_equal": normalize_provider_reason_key("lumper") != "lumper fee",
        }

    async with factory() as session:
        pay_txn = await session.scalar(
            select(FuelTransaction).where(
                FuelTransaction.tenant_id == TENANT_ID,
                FuelTransaction.batch_id == report["batch_id_838710"],
                FuelTransaction.provider_section_raw == SECTION_EXPRESS,
                FuelTransaction.provider_reason_raw == "pay",
            )
        )
        assert pay_txn is not None
        await set_transaction_classification_manual(
            session,
            tenant_id=TENANT_ID,
            transaction_id=pay_txn.id,
            canonical_category=CATEGORY_OTHER,
            remember_mapping=False,
            actor_user_id="segment_b_acceptance",
        )
        await session.commit()
        await backfill_classifications_for_import(session, tenant_id=TENANT_ID, import_id=imp838)
        await session.commit()
        pay_after = await session.scalar(
            select(FuelTransaction).where(
                FuelTransaction.tenant_id == TENANT_ID,
                FuelTransaction.id == pay_txn.id,
            )
        )
        report["manual_pay_sticky"] = {
            "classification": pay_after.classification,
            "status": pay_after.classification_status,
            "source": pay_after.classification_source,
        }
        mapping_pay = await session.scalar(
            select(func.count())
            .select_from(FuelProviderCategoryMapping)
            .where(
                FuelProviderCategoryMapping.tenant_id == TENANT_ID,
                FuelProviderCategoryMapping.normalized_reason_key == "pay",
                FuelProviderCategoryMapping.active.is_(True),
            )
        )
        report["no_pay_mapping_created"] = mapping_pay == 0

    async with factory() as session:
        await version_tenant_reason_mapping(
            session,
            tenant_id=TENANT_ID,
            provider_code="BVD",
            provider_section=SECTION_EXPRESS,
            normalized_reason_key="lumper fee",
            canonical_category_code="OTHER",
            raw_example="lumper fee",
            approved_by="segment_b_acceptance",
        )
        await session.commit()
        hist = list(
            (
                await session.execute(
                    select(FuelProviderCategoryMapping)
                    .where(
                        FuelProviderCategoryMapping.tenant_id == TENANT_ID,
                        FuelProviderCategoryMapping.normalized_reason_key == "lumper fee",
                    )
                    .order_by(FuelProviderCategoryMapping.id.asc())
                )
            ).scalars().all()
        )
        active = [h for h in hist if h.active]
        report["mapping_version_history"] = [
            {"id": h.id, "category": h.canonical_category_code, "active": h.active}
            for h in hist
        ]
        report["one_active_lumper_fee_mapping"] = len(active) == 1 and active[0].canonical_category_code == "OTHER"
        await version_tenant_reason_mapping(
            session,
            tenant_id=TENANT_ID,
            provider_code="BVD",
            provider_section=SECTION_EXPRESS,
            normalized_reason_key="lumper fee",
            canonical_category_code=CATEGORY_LUMPER,
            raw_example="lumper fee",
            approved_by="segment_b_acceptance",
        )
        await session.commit()

    if imp972:
        async with factory() as session:
            batch972 = await session.scalar(
                select(FuelSourceBatch).where(
                    FuelSourceBatch.tenant_id == TENANT_ID,
                    FuelSourceBatch.source_import_ref == imp972,
                )
            )
            await backfill_classifications_for_import(session, tenant_id=TENANT_ID, import_id=imp972)
            await session.commit()
            report["972201"] = await _txn_snapshot(session, batch972.id)

    async with factory() as session:
        cats = list(
            (await session.execute(select(FuelChargeCategory).where(FuelChargeCategory.active.is_(True))))
            .scalars()
            .all()
        )
        report["active_category_codes"] = sorted(c.code for c in cats)
        batch_id = report["batch_id_838710"]
        report["money_after"] = await _txn_snapshot(session, batch_id)

    print(json.dumps(report, indent=2, default=str))
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
