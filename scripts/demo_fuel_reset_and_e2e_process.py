#!/usr/bin/env python3
"""Wipe tenant_demo Fuel data, Process one BVD + one Nationwide PDF, print canonical inspection."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.fuel import (
    FuelBvd,
    FuelBvdFieldCorrection,
    FuelBvdImportStage,
    FuelBvdStageFieldCorrection,
    FuelBvdStageRow,
    FuelNationwide,
    FuelNationwideFieldCorrection,
    FuelNationwideImportStage,
    FuelNationwideStageFieldCorrection,
    FuelNationwideStageRow,
    FuelSourceBatch,
    FuelSourceControl,
    FuelTransaction,
)
from app.services.fuel_bvd_import import import_bvd_digital_pdf
from app.services.fuel_bvd_review import process_bvd_import_review
from app.services.fuel_nationwide_review import process_nationwide_import_review
from app.services.fuel_nationwide_stage import create_nationwide_import_stage_from_pdf

TENANT_ID = 53
TENANT_SLUG = "demo"
REPO = Path("/app") if Path("/app").is_dir() else Path(__file__).resolve().parents[1]
BVD_PDF = REPO / "docs/fixtures/fuel/BVD_invoice_972201.pdf"
NW_PDF = REPO / "docs/fixtures/fuel/nationwide_fuel.pdf"


def _tenant_url() -> str:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        raise RuntimeError("TENANT_DATABASE_URL not set")
    return to_async_pg_url(raw.strip())


async def _purge_all_fuel(session: AsyncSession) -> dict[str, int]:
    """Delete all Fuel import/canonical rows for tenant (keep provider connections / config)."""
    counts: dict[str, int] = {}

    async def _del(label: str, stmt) -> None:
        res = await session.execute(stmt)
        counts[label] = res.rowcount or 0

    # Events / canonical (order matters)
    for table in (
        "fuel_transaction_financial_event",
        "fuel_transaction_classification_event",
    ):
        reg = await session.scalar(text(f"SELECT to_regclass('{table}')"))
        if reg:
            await _del(table, text(f"DELETE FROM {table} WHERE tenant_id = :tid").bindparams(tid=TENANT_ID))

    await _del("fuel_transactions", delete(FuelTransaction).where(FuelTransaction.tenant_id == TENANT_ID))
    await _del("fuel_source_controls", delete(FuelSourceControl).where(FuelSourceControl.tenant_id == TENANT_ID))
    await _del("fuel_source_batches", delete(FuelSourceBatch).where(FuelSourceBatch.tenant_id == TENANT_ID))

    reg = await session.scalar(text("SELECT to_regclass('fuel_extraction_corrections')"))
    if reg:
        await _del(
            "fuel_extraction_corrections",
            text("DELETE FROM fuel_extraction_corrections WHERE tenant_id = :tid").bindparams(tid=TENANT_ID),
        )

    await _del(
        "fuel_bvd_field_correction",
        delete(FuelBvdFieldCorrection).where(FuelBvdFieldCorrection.tenant_id == TENANT_ID),
    )
    await _del("fuel_bvd", delete(FuelBvd).where(FuelBvd.tenant_id == TENANT_ID))
    await _del(
        "fuel_bvd_stage_field_correction",
        delete(FuelBvdStageFieldCorrection).where(FuelBvdStageFieldCorrection.tenant_id == TENANT_ID),
    )
    await _del("fuel_bvd_stage_row", delete(FuelBvdStageRow).where(FuelBvdStageRow.tenant_id == TENANT_ID))
    await _del(
        "fuel_bvd_import_stage",
        delete(FuelBvdImportStage).where(FuelBvdImportStage.tenant_id == TENANT_ID),
    )

    await _del(
        "fuel_nationwide_field_correction",
        delete(FuelNationwideFieldCorrection).where(FuelNationwideFieldCorrection.tenant_id == TENANT_ID),
    )
    await _del("fuel_nationwide", delete(FuelNationwide).where(FuelNationwide.tenant_id == TENANT_ID))
    await _del(
        "fuel_nationwide_stage_field_correction",
        delete(FuelNationwideStageFieldCorrection).where(
            FuelNationwideStageFieldCorrection.tenant_id == TENANT_ID
        ),
    )
    await _del(
        "fuel_nationwide_stage_row",
        delete(FuelNationwideStageRow).where(FuelNationwideStageRow.tenant_id == TENANT_ID),
    )
    await _del(
        "fuel_nationwide_import_stage",
        delete(FuelNationwideImportStage).where(FuelNationwideImportStage.tenant_id == TENANT_ID),
    )

    await session.commit()
    return counts


def _purge_demo_storage() -> int:
    """Best-effort local file backend purge under demo/fuel* prefixes."""
    from app.core.config import settings
    from app.core.storage import STORAGE_ROOT, get_storage

    get_storage()  # ensure backend configured
    root = Path(settings.local_storage_dir or str(STORAGE_ROOT)).resolve()
    base = root / TENANT_SLUG
    removed = 0
    if not base.is_dir():
        return 0
    for name in ("fuel_bvd", "fuel_bvd_stage", "fuel_nationwide", "fuel_nationwide_stage"):
        root = base / name
        if root.is_dir():
            for p in sorted(root.rglob("*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
                    removed += 1
                elif p.is_dir():
                    try:
                        p.rmdir()
                    except OSError:
                        pass
    return removed


async def _inspect_batch(session: AsyncSession, label: str, import_ref: str) -> dict:
    batch = await session.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == TENANT_ID,
            FuelSourceBatch.source_import_ref == import_ref,
        )
    )
    if batch is None:
        return {"label": label, "error": "batch not found", "import_ref": import_ref}

    txns = (
        await session.execute(
            select(FuelTransaction).where(
                FuelTransaction.tenant_id == TENANT_ID,
                FuelTransaction.batch_id == batch.id,
            )
        )
    ).scalars().all()
    ctrls = (
        await session.execute(
            select(FuelSourceControl).where(
                FuelSourceControl.tenant_id == TENANT_ID,
                FuelSourceControl.batch_id == batch.id,
            )
        )
    ).scalars().all()

    def _dec(v: Decimal | None) -> str | None:
        return str(v) if v is not None else None

    txn_sample = []
    for t in txns[:3]:
        txn_sample.append(
            {
                "id": t.id,
                "source_row_id": t.source_row_id,
                "currency": t.currency,
                "quantity": _dec(t.quantity),
                "quantity_unit": t.quantity_unit,
                "unit_price": _dec(t.unit_price),
                "unit_price_basis": t.unit_price_basis,
                "total_amount": _dec(t.total_amount),
                "provider_discount_amount": _dec(t.provider_discount_amount),
                "pre_tax_amount": _dec(t.pre_tax_amount),
                "transaction_date": str(t.transaction_date) if t.transaction_date else None,
                "classification": t.classification,
                "classification_status": t.classification_status,
            }
        )

    ctrl_types: dict[str, int] = {}
    ctrl_sample = []
    for c in ctrls:
        ctrl_types[c.control_type] = ctrl_types.get(c.control_type, 0) + 1
        if len(ctrl_sample) < 5:
            ctrl_sample.append(
                {
                    "control_type": c.control_type,
                    "declared_amount": _dec(c.declared_amount),
                    "quantity": _dec(c.quantity),
                    "pre_tax_amount": _dec(c.pre_tax_amount),
                    "gst_amount": _dec(c.gst_amount),
                    "discount_amount": _dec(c.discount_amount),
                }
            )

    return {
        "label": label,
        "batch_id": batch.id,
        "invoice_number": batch.invoice_number,
        "provider_code": batch.provider_code,
        "invoice_date": str(batch.invoice_date) if batch.invoice_date else None,
        "transaction_count": len(txns),
        "control_count": len(ctrls),
        "control_types": ctrl_types,
        "txn_with_unit_price_basis": sum(1 for t in txns if t.unit_price_basis),
        "txn_with_quantity_unit": sum(1 for t in txns if t.quantity_unit),
        "txn_sample": txn_sample,
        "control_sample": ctrl_sample,
        "usd_discount_sum": str(
            sum((t.provider_discount_amount or Decimal("0") for t in txns if t.currency == "USD"), Decimal("0"))
        ),
        "cad_discount_sum": str(
            sum((t.provider_discount_amount or Decimal("0") for t in txns if t.currency == "CAD"), Decimal("0"))
        ),
    }


async def main() -> None:
    if not BVD_PDF.is_file() or not NW_PDF.is_file():
        raise SystemExit(f"PDF fixtures missing: {BVD_PDF} {NW_PDF}")

    storage_removed = _purge_demo_storage()
    engine = create_async_engine(_tenant_url(), pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        purge_counts = await _purge_all_fuel(session)

    bvd_import_id: uuid.UUID
    nw_import_id: uuid.UUID

    async with session_maker() as session:
        bvd_import_id, bvd_count, bvd_status = await import_bvd_digital_pdf(
            session,
            tenant_id=TENANT_ID,
            tenant_slug=TENANT_SLUG,
            pdf_bytes=BVD_PDF.read_bytes(),
            filename=BVD_PDF.name,
            uploaded_by="demo_fuel_e2e",
        )
        assert bvd_status == "SUCCESS", (bvd_status, bvd_count)
        await process_bvd_import_review(
            session,
            tenant_id=TENANT_ID,
            import_id=bvd_import_id,
            reviewed_by="demo_fuel_e2e",
            tenant_slug=TENANT_SLUG,
        )

    async with session_maker() as session:
        nw_import_id, nw_count, nw_status, _ = await create_nationwide_import_stage_from_pdf(
            session,
            tenant_id=TENANT_ID,
            tenant_slug=TENANT_SLUG,
            pdf_bytes=NW_PDF.read_bytes(),
            filename=NW_PDF.name,
            uploaded_by="demo_fuel_e2e",
        )
        assert nw_status == "SUCCESS", (nw_status, nw_count)
        await process_nationwide_import_review(
            session,
            tenant_id=TENANT_ID,
            import_id=nw_import_id,
            reviewed_by="demo_fuel_e2e",
            tenant_slug=TENANT_SLUG,
        )

    async with session_maker() as session:
        report = {
            "tenant_id": TENANT_ID,
            "tenant_slug": TENANT_SLUG,
            "storage_files_removed": storage_removed,
            "purge_rowcounts": purge_counts,
            "bvd_import_id": str(bvd_import_id),
            "nationwide_import_id": str(nw_import_id),
            "bvd": await _inspect_batch(session, "BVD_972201", str(bvd_import_id)),
            "nationwide": await _inspect_batch(session, "Nationwide_fixture", str(nw_import_id)),
        }
        print(json.dumps(report, indent=2))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
