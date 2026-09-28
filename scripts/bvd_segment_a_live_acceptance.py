#!/usr/bin/env python3
"""Segment A live acceptance on tenant_demo (run inside truckerp-api container)."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.models.fuel import (
    FuelBvd,
    FuelBvdFieldCorrection,
    FuelBvdImportStage,
    FuelBvdStageFieldCorrection,
    FuelBvdStageRow,
    FuelSourceBatch,
    FuelSourceControl,
    FuelTransaction,
)
from app.services.fuel_bvd_effective import build_effective_bvd_row
from app.services.fuel_bvd_import import import_bvd_digital_pdf
from app.services.fuel_bvd_review import (
    list_bvd_import_rows_for_review,
    process_bvd_import_review,
    reconcile_bvd_import_review_rows,
    save_bvd_import_review,
)
from app.services.fuel_bvd_stage import discard_bvd_import_stage, get_active_stage
from app.services.fuel_controls import (
    CONTROL_TYPE_CARD_TOTAL,
    CONTROL_TYPE_GROUP_SUBTOTAL,
    CONTROL_TYPE_INVOICE_TOTAL,
    CONTROL_TYPE_PRODUCT_SUBTOTAL,
)
from app.services.fuel_bvd_canonical_projection import SECTION_EXPRESS, SECTION_FUEL_CARD

TENANT_ID = 53
TENANT_SLUG = "demo"
REPO = Path("/app")
PDF_838710 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_838710.pdf"
PDF_972201 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"

EXPECTED_CARDS = {
    "4236501",
    "4236576",
    "4236675",
    "4236980",
    "4237061",
    "4237160",
    "4237186",
}


def _pg_url() -> str:
    import os

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        raise RuntimeError("TENANT_DATABASE_URL not set")
    return to_async_pg_url(raw)


async def _purge_invoice_import(session: AsyncSession, import_id: uuid.UUID) -> None:
    batch = await session.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == TENANT_ID,
            FuelSourceBatch.source_import_ref == str(import_id),
        )
    )
    if batch:
        await session.execute(
            delete(FuelTransaction).where(
                FuelTransaction.tenant_id == TENANT_ID,
                FuelTransaction.batch_id == batch.id,
            )
        )
        await session.execute(
            delete(FuelSourceControl).where(
                FuelSourceControl.tenant_id == TENANT_ID,
                FuelSourceControl.batch_id == batch.id,
            )
        )
        await session.execute(
            delete(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.id == batch.id,
            )
        )
    await session.execute(
        delete(FuelBvdFieldCorrection).where(
            FuelBvdFieldCorrection.tenant_id == TENANT_ID,
            FuelBvdFieldCorrection.import_id == import_id,
        )
    )
    await session.execute(
        delete(FuelBvd).where(FuelBvd.tenant_id == TENANT_ID, FuelBvd.import_id == import_id)
    )
    await session.execute(
        delete(FuelBvdStageFieldCorrection).where(
            FuelBvdStageFieldCorrection.tenant_id == TENANT_ID,
            FuelBvdStageFieldCorrection.stage_id == import_id,
        )
    )
    await session.execute(
        delete(FuelBvdStageRow).where(
            FuelBvdStageRow.tenant_id == TENANT_ID,
            FuelBvdStageRow.stage_id == import_id,
        )
    )
    await session.execute(
        delete(FuelBvdImportStage).where(
            FuelBvdImportStage.tenant_id == TENANT_ID,
            FuelBvdImportStage.stage_id == import_id,
        )
    )


async def _purge_all_838710(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(FuelBvd.import_id).where(
            FuelBvd.tenant_id == TENANT_ID,
            FuelBvd.invoice_number == "838710",
        ).distinct()
    )
    ids = [str(x) for x in result.scalars().all()]
    for imp in ids:
        await _purge_invoice_import(session, uuid.UUID(imp))
    # orphan stages by invoice
    stages = await session.execute(
        select(FuelBvdImportStage.stage_id).where(
            FuelBvdImportStage.tenant_id == TENANT_ID,
            FuelBvdImportStage.invoice_number == "838710",
        )
    )
    for sid in stages.scalars().all():
        await _purge_invoice_import(session, sid)
    await session.commit()
    return ids


async def _process_pdf(
    session: AsyncSession,
    pdf: Path,
    invoice_label: str,
    *,
    corrections: list[dict[str, Any]] | None = None,
) -> uuid.UUID:
    import_id, _count, _status = await import_bvd_digital_pdf(
        session,
        tenant_id=TENANT_ID,
        tenant_slug=TENANT_SLUG,
        pdf_bytes=pdf.read_bytes(),
        filename=pdf.name,
        uploaded_by="segment_a_acceptance",
    )
    rows = await list_bvd_import_rows_for_review(session, tenant_id=TENANT_ID, import_id=import_id)
    if corrections:
        await save_bvd_import_review(
            session,
            tenant_id=TENANT_ID,
            import_id=import_id,
            reviewed_by="segment_a_acceptance",
            corrections=corrections,
        )
        rows = await list_bvd_import_rows_for_review(session, tenant_id=TENANT_ID, import_id=import_id)
    recon = reconcile_bvd_import_review_rows(rows)
    if not recon.passed:
        raise RuntimeError(f"{invoice_label} source reconciliation failed: {recon.difference}")
    await process_bvd_import_review(
        session,
        tenant_id=TENANT_ID,
        import_id=import_id,
        reviewed_by="segment_a_acceptance",
        tenant_slug=TENANT_SLUG,
    )
    return import_id


async def _batch_report(session: AsyncSession, import_id: uuid.UUID) -> dict[str, Any]:
    batch = await session.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == TENANT_ID,
            FuelSourceBatch.source_import_ref == str(import_id),
        )
    )
    if not batch:
        raise RuntimeError("FuelSourceBatch missing")
    txns = list(
        (
            await session.execute(
                select(FuelTransaction).where(
                    FuelTransaction.tenant_id == TENANT_ID,
                    FuelTransaction.batch_id == batch.id,
                )
            )
        ).scalars().all()
    )
    controls = list(
        (
            await session.execute(
                select(FuelSourceControl).where(
                    FuelSourceControl.tenant_id == TENANT_ID,
                    FuelSourceControl.batch_id == batch.id,
                )
            )
        ).scalars().all()
    )
    purchase = [t for t in txns if t.provider_section_raw == SECTION_FUEL_CARD]
    express = [t for t in txns if t.provider_section_raw == SECTION_EXPRESS]
    total = sum((t.total_amount or Decimal("0") for t in txns), Decimal("0"))
    cards = {t.card_or_account_id for t in purchase if t.card_or_account_id}
    express_row = next((t for t in express if t.provider_transaction_identity == "E345296820"), None)
    express_subtotal_ctrl = next(
        (
            c
            for c in controls
            if (c.control_label_raw or "").upper().startswith("EXPRESS SUBTOTAL")
        ),
        None,
    )
    grand_express_ctrl = next(
        (
            c
            for c in controls
            if (c.control_label_raw or "").strip().lower() in {"grand express", "express"}
            and c.control_type == CONTROL_TYPE_GROUP_SUBTOTAL
            and c.declared_amount == Decimal("1676.78")
        ),
        None,
    )
    ctrl_types: dict[str, int] = {}
    ctrl_scopes: dict[str, int] = {}
    for c in controls:
        ctrl_types[c.control_type] = ctrl_types.get(c.control_type, 0) + 1
        ctrl_scopes[c.control_scope] = ctrl_scopes.get(c.control_scope, 0) + 1
    invoice_ctrl = [
        c for c in controls if c.control_type == CONTROL_TYPE_INVOICE_TOTAL
    ]
    return {
        "batch_id": batch.id,
        "batch_status": batch.status,
        "provider_code": batch.provider_code,
        "source_import_ref": batch.source_import_ref,
        "invoice_number": batch.invoice_number,
        "txn_count": len(txns),
        "purchase_count": len(purchase),
        "express_count": len(express),
        "express_card_ids": sorted({t.card_or_account_id for t in express}),
        "txn_sum": str(total),
        "cards": sorted(cards),
        "express_row": express_row,
        "express_row_e345296820": (
            {
                "provider_section_raw": express_row.provider_section_raw,
                "provider_transaction_identity": express_row.provider_transaction_identity,
                "provider_reference_raw": express_row.provider_reference_raw,
                "unit_number_snapshot": express_row.unit_number_snapshot,
                "driver_name_snapshot": express_row.driver_name_snapshot,
                "principal_amount": str(express_row.principal_amount),
                "provider_fee_amount": str(express_row.provider_fee_amount),
                "total_amount": str(express_row.total_amount),
                "currency_raw": express_row.currency_raw,
                "provider_reason_raw": express_row.provider_reason_raw,
                "classification": express_row.classification,
                "classification_status": express_row.classification_status,
                "classification_source": express_row.classification_source,
                "provider_raw_has_express_evidence": bool(express_row.provider_raw),
            }
            if express_row
            else None
        ),
        "control_type_counts": ctrl_types,
        "control_scope_counts": ctrl_scopes,
        "invoice_controls": [
            {"declared": str(c.declared_amount), "label": c.control_label_raw}
            for c in invoice_ctrl
        ],
        "express_subtotal_control": (
            {
                "type": express_subtotal_ctrl.control_type,
                "scope": express_subtotal_ctrl.control_scope,
                "amount": str(express_subtotal_ctrl.declared_amount),
                "label": express_subtotal_ctrl.control_label_raw,
            }
            if express_subtotal_ctrl
            else None
        ),
        "grand_express_control": (
            {
                "type": grand_express_ctrl.control_type,
                "scope": grand_express_ctrl.control_scope,
                "amount": str(grand_express_ctrl.declared_amount),
            }
            if grand_express_ctrl
            else None
        ),
        "express_subtotal_not_a_transaction": express_subtotal_ctrl is not None
        and not any(
            t.total_amount == express_subtotal_ctrl.declared_amount
            and t.provider_section_raw == SECTION_EXPRESS
            and t.provider_transaction_identity is None
            for t in express
        ),
        "controls_4237061": [
            {
                "type": c.control_type,
                "scope": c.control_scope,
                "label": c.control_label_raw,
                "card": c.scope_card_or_account_id,
                "amount": str(c.declared_amount),
            }
            for c in controls
            if c.scope_card_or_account_id == "4237061"
        ],
    }


async def main() -> int:
    engine = create_async_engine(_pg_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report: dict[str, Any] = {}

    async with factory() as session:
        purged = await _purge_all_838710(session)
        report["purged_import_ids"] = purged

    async with factory() as session:
        import_id, _count, _status = await import_bvd_digital_pdf(
            session,
            tenant_id=TENANT_ID,
            tenant_slug=TENANT_SLUG,
            pdf_bytes=PDF_838710.read_bytes(),
            filename=PDF_838710.name,
            uploaded_by="segment_a_acceptance",
        )
        rows838 = await list_bvd_import_rows_for_review(
            session, tenant_id=TENANT_ID, import_id=import_id
        )
        purchase_stage = next(
            r for r in rows838 if r.get("auth_code") == "A344082616-TA"
        )
        await save_bvd_import_review(
            session,
            tenant_id=TENANT_ID,
            import_id=import_id,
            reviewed_by="segment_a_acceptance",
            corrections=[
                {
                    "fuel_bvd_id": purchase_stage["id"],
                    "field_name": "driver_name",
                    "reviewed_value": "GURPREET SINGH (reviewed)",
                    "correction_reason": "segment_a_raw_effective_proof",
                }
            ],
        )
        rows838 = await list_bvd_import_rows_for_review(
            session, tenant_id=TENANT_ID, import_id=import_id
        )
        recon_pre = reconcile_bvd_import_review_rows(rows838)
        if not recon_pre.passed:
            raise RuntimeError(f"838710 source reconciliation failed: {recon_pre.difference}")
        await process_bvd_import_review(
            session,
            tenant_id=TENANT_ID,
            import_id=import_id,
            reviewed_by="segment_a_acceptance",
            tenant_slug=TENANT_SLUG,
        )
        report["import_id_838710"] = str(import_id)
        report["838710"] = await _batch_report(session, import_id)
        recon = reconcile_bvd_import_review_rows(
            await list_bvd_import_rows_for_review(session, tenant_id=TENANT_ID, import_id=import_id)
        )
        report["838710_recon"] = {
            "passed": recon.passed,
            "difference": recon.difference,
            "transaction_total": recon.transaction_total,
            "provider_grand_total": recon.provider_grand_total,
        }

    # duplicate auth proof
    async with factory() as session:
        batch_id = report["838710"]["batch_id"]
        dup = await session.execute(
            text(
                """
                SELECT provider_transaction_identity, count(*)::int
                FROM fuel_transactions
                WHERE tenant_id=:tid AND batch_id=:bid
                GROUP BY provider_transaction_identity
                HAVING count(*) > 1
                LIMIT 5
                """
            ),
            {"tid": TENANT_ID, "bid": batch_id},
        )
        report["duplicate_auth_groups"] = [dict(r._mapping) for r in dup]
        prefix_dup = await session.execute(
            text(
                """
                SELECT split_part(provider_transaction_identity, '-', 1) AS auth_prefix,
                       count(*)::int AS n
                FROM fuel_transactions
                WHERE tenant_id=:tid AND batch_id=:bid
                  AND provider_section_raw = 'FUEL_CARD_TRANSACTIONS'
                  AND provider_transaction_identity IS NOT NULL
                GROUP BY 1
                HAVING count(*) > 1
                ORDER BY n DESC
                LIMIT 5
                """
            ),
            {"tid": TENANT_ID, "bid": batch_id},
        )
        report["multi_product_auth_prefixes"] = [dict(r._mapping) for r in prefix_dup]

    # fuel_transactions uniqueness: no provider_transaction_identity-only unique index
    async with factory() as session:
        idx = await session.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'fuel_transactions'
                  AND schemaname = current_schema()
                ORDER BY indexname
                """
            )
        )
        report["fuel_transactions_indexes"] = [dict(r._mapping) for r in idx]
        unique_on_identity = [
            row["indexname"]
            for row in report["fuel_transactions_indexes"]
            if "UNIQUE" in (row["indexdef"] or "").upper()
            and "provider_transaction_identity" in (row["indexdef"] or "")
        ]
        report["unique_indexes_on_provider_transaction_identity"] = unique_on_identity

    # gate failure + rollback (before any permanent 972201 on tenant)
    from unittest.mock import patch

    from app.services.fuel_bvd_canonical_projection import (
        assert_canonical_money_gate as real_money_gate,
        quantize_money,
    )

    async with factory() as session:
        purged972_gate = await session.execute(
            select(FuelBvd.import_id).where(
                FuelBvd.tenant_id == TENANT_ID, FuelBvd.invoice_number == "972201"
            ).distinct()
        )
        for i in purged972_gate.scalars().all():
            await _purge_invoice_import(session, i)
        await session.commit()

    async with factory() as session:
        gate_stage_id, _, _ = await import_bvd_digital_pdf(
            session,
            tenant_id=TENANT_ID,
            tenant_slug=TENANT_SLUG,
            pdf_bytes=PDF_972201.read_bytes(),
            filename="BVD_invoice_972201_gate_fail.pdf",
            uploaded_by="segment_a_acceptance",
        )
        await session.commit()

    def _money_gate_off_by_penny(transactions, controls, **kwargs):
        bumped = dict(kwargs)
        bumped["expected_total"] = quantize_money(bumped["expected_total"] + Decimal("0.01"))
        return real_money_gate(transactions, controls, **bumped)

    gate_err: dict[str, Any] | None = None
    async with factory() as session:
        with patch("app.services.fuel_bvd_stage.assert_canonical_money_gate", side_effect=_money_gate_off_by_penny):
            try:
                await process_bvd_import_review(
                    session,
                    tenant_id=TENANT_ID,
                    import_id=gate_stage_id,
                    reviewed_by="segment_a_acceptance",
                    tenant_slug=TENANT_SLUG,
                )
                gate_err = {"ok": False, "detail": "process unexpectedly succeeded"}
            except Exception as exc:
                gate_err = {"ok": True, "exc_type": type(exc).__name__, "detail": str(exc)[:500]}
        batch_after = await session.scalar(
            select(func.count())
            .select_from(FuelSourceBatch)
            .where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == str(gate_stage_id),
            )
        )
        txn_after = await session.scalar(
            select(func.count())
            .select_from(FuelTransaction)
            .join(
                FuelSourceBatch,
                (FuelTransaction.batch_id == FuelSourceBatch.id)
                & (FuelTransaction.tenant_id == FuelSourceBatch.tenant_id),
            )
            .where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == str(gate_stage_id),
            )
        )
        bvd_after = await session.scalar(
            select(func.count())
            .select_from(FuelBvd)
            .where(FuelBvd.tenant_id == TENANT_ID, FuelBvd.import_id == gate_stage_id)
        )
        stage_active = await get_active_stage(session, tenant_id=TENANT_ID, stage_id=gate_stage_id)
        report["gate_fail_process_rollback"] = {
            "error": gate_err,
            "batch_count": batch_after,
            "txn_count": txn_after,
            "fuel_bvd_count": bvd_after,
            "stage_still_active": stage_active is not None,
        }
        if stage_active is not None:
            await discard_bvd_import_stage(
                session, tenant_id=TENANT_ID, stage_id=gate_stage_id, tenant_slug=TENANT_SLUG
            )
            await session.commit()

    # raw vs effective persistence (838710 purchase driver_name correction applied before process)
    async with factory() as session:
        imp = uuid.UUID(report["import_id_838710"])
        fuel_bvd_id = await session.scalar(
            select(FuelBvd.id).where(
                FuelBvd.tenant_id == TENANT_ID,
                FuelBvd.import_id == imp,
                FuelBvd.auth_code == "A344082616-TA",
            )
        )
        raw_driver = await session.scalar(
            select(FuelBvd.driver_name).where(FuelBvd.id == fuel_bvd_id)
        )
        corr = await session.scalar(
            select(FuelBvdFieldCorrection.reviewed_value).where(
                FuelBvdFieldCorrection.tenant_id == TENANT_ID,
                FuelBvdFieldCorrection.fuel_bvd_id == fuel_bvd_id,
                FuelBvdFieldCorrection.field_name == "driver_name",
            )
        )
        batch_id = report["838710"]["batch_id"]
        txn = await session.scalar(
            select(FuelTransaction).where(
                FuelTransaction.tenant_id == TENANT_ID,
                FuelTransaction.batch_id == batch_id,
                FuelTransaction.provider_transaction_identity == "A344082616-TA",
            )
        )
        report["raw_effective"] = {
            "fuel_bvd_driver_name_raw": raw_driver,
            "correction_driver_name": corr,
            "canonical_driver_name_snapshot": txn.driver_name_snapshot if txn else None,
            "provider_raw_driver_name": (
                txn.provider_raw.get("fields", {}).get("driver_name") if txn else None
            ),
        }

    # 972201 regression (no corrections)
    async with factory() as session:
        purged972 = await session.execute(
            select(FuelBvd.import_id).where(
                FuelBvd.tenant_id == TENANT_ID, FuelBvd.invoice_number == "972201"
            ).distinct()
        )
        for i in purged972.scalars().all():
            await _purge_invoice_import(session, i)
        await session.commit()

    async with factory() as session:
        i972 = await _process_pdf(session, PDF_972201, "972201")
        report["972201"] = await _batch_report(session, i972)

    # idempotent second process - re-stage shouldn't exist; call process on completed import
    async with factory() as session:
        imp = uuid.UUID(report["import_id_838710"])
        summary2 = await process_bvd_import_review(
            session,
            tenant_id=TENANT_ID,
            import_id=imp,
            reviewed_by="segment_a_acceptance",
            tenant_slug=TENANT_SLUG,
        )
        report["idempotent_second_process"] = summary2
        report["838710_after_idempotent"] = await _batch_report(session, imp)
        batch_count = await session.scalar(
            select(func.count())
            .select_from(FuelSourceBatch)
            .where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == str(imp),
            )
        )
        report["batch_count_for_import"] = batch_count

    # diagnostic checks from last 838710 recon
    async with factory() as session:
        imp = uuid.UUID(report["import_id_838710"])
        rows = await list_bvd_import_rows_for_review(session, tenant_id=TENANT_ID, import_id=imp)
        recon = reconcile_bvd_import_review_rows(rows)
        line_info = [c for c in recon.checks if c.code.startswith("TXN_LINE_ARITHMETIC_")]
        period_info = [c for c in recon.checks if "OUTSIDE_PERIOD" in c.code]
        report["diagnostics"] = {
            "line_arithmetic_info_count": sum(1 for c in line_info if c.status == "INFO"),
            "line_arithmetic_fail_count": sum(1 for c in line_info if c.status == "FAIL"),
            "period_info_count": len(period_info),
            "recon_passed": recon.passed,
        }

    print(json.dumps(report, indent=2, default=str))
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
