"""Nationwide staging → Process → canonical (tenant_pytest)."""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.fuel import (
    FuelNationwide,
    FuelNationwideImportStage,
    FuelNationwideStageRow,
    FuelSourceBatch,
    FuelSourceControl,
    FuelTransaction,
)
from app.services.fuel_source_duplicate_gate import sha256_hex
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED
from app.services.fuel_nationwide_review import process_nationwide_import_review
from app.services.fuel_nationwide_stage import create_nationwide_import_stage_from_pdf
from tests.support.integration_isolation import require_integration_tenant_database_url

REPO = Path(__file__).resolve().parents[1]
NW_PDF = REPO / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"
TENANT_ID = 53
TENANT_SLUG = "pytest"


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_nationwide_process"))
    except Exception:
        return None


REQUIRES_DB = _tenant_url() is None


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant_pytest URL not configured")
async def test_nationwide_full_process_fixture() -> None:
    url = _tenant_url()
    assert url
    engine = create_async_engine(url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    pdf = NW_PDF.read_bytes()
    file_sha = sha256_hex(pdf)
    import_id: uuid.UUID | None = None

    from tests.test_fuel_nationwide_api_routes import _purge_nationwide_fixture

    async with session_maker() as session:
        await _purge_nationwide_fixture(session, TENANT_ID, file_sha)
        await session.commit()

    async with session_maker() as session:
        stage_id, count, status, _ = await create_nationwide_import_stage_from_pdf(
            session,
            tenant_id=TENANT_ID,
            tenant_slug=TENANT_SLUG,
            pdf_bytes=pdf,
            filename="nationwide_fuel.pdf",
            uploaded_by="test",
        )
        import_id = stage_id
        assert status == "SUCCESS"
        assert count >= 13

        await process_nationwide_import_review(
            session,
            tenant_id=TENANT_ID,
            import_id=stage_id,
            reviewed_by="test",
            tenant_slug=TENANT_SLUG,
        )

        txn_count = await session.scalar(
            select(func.count())
            .select_from(FuelTransaction)
            .join(FuelSourceBatch, FuelTransaction.batch_id == FuelSourceBatch.id)
            .where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == str(stage_id),
            )
        )
        assert txn_count == 12

        ctrl_count = await session.scalar(
            select(func.count())
            .select_from(FuelSourceControl)
            .join(FuelSourceBatch, FuelSourceControl.batch_id == FuelSourceBatch.id)
            .where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == str(stage_id),
            )
        )
        assert ctrl_count > 0

        batch = await session.scalar(
            select(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == str(stage_id),
            )
        )
        assert batch is not None
        assert batch.status == BATCH_STATUS_FINALIZED
        assert batch.invoice_date is None
        assert batch.statement_start.isoformat() == "2026-06-08"
        assert batch.statement_end.isoformat() == "2026-06-14"

        txns = (
            await session.execute(
                select(FuelTransaction).where(
                    FuelTransaction.tenant_id == TENANT_ID,
                    FuelTransaction.batch_id == batch.id,
                )
            )
        ).scalars().all()
        usd = sum(t.total_amount or Decimal("0") for t in txns if t.currency == "USD")
        cad = sum(t.total_amount or Decimal("0") for t in txns if t.currency == "CAD")
        assert usd == Decimal("5197.67")
        assert cad == Decimal("1263.85")
        assert all(t.driver_name_snapshot is None for t in txns)

        cad_rows = [t for t in txns if t.currency == "CAD"]
        usd_rows = [t for t in txns if t.currency == "USD"]

        assert len(cad_rows) == 1
        assert len(usd_rows) == 11

        assert all(t.quantity_unit == "litres" for t in cad_rows)
        assert all(t.unit_price_basis == "EX_TAX" for t in cad_rows)

        assert all(t.quantity_unit == "gallons" for t in usd_rows)
        assert all(t.unit_price_basis == "FINAL_GALLON_PRICE" for t in usd_rows)

        usd_ctl = await session.scalar(
            select(FuelSourceControl.declared_amount)
            .join(FuelSourceBatch, FuelSourceControl.batch_id == FuelSourceBatch.id)
            .where(
                FuelSourceBatch.tenant_id == TENANT_ID,
                FuelSourceBatch.source_import_ref == str(stage_id),
                FuelSourceControl.control_type == "CURRENCY_TOTAL",
            )
        )
        assert usd_ctl == Decimal("5197.69")

        stage_left = await session.scalar(
            select(func.count()).select_from(FuelNationwideImportStage).where(
                FuelNationwideImportStage.tenant_id == TENANT_ID,
                FuelNationwideImportStage.stage_id == stage_id,
            )
        )
        assert stage_left == 0

    async with session_maker() as cleanup:
        if import_id:
            batch = await cleanup.scalar(
                select(FuelSourceBatch).where(
                    FuelSourceBatch.tenant_id == TENANT_ID,
                    FuelSourceBatch.source_import_ref == str(import_id),
                )
            )
            if batch:
                await cleanup.execute(delete(FuelTransaction).where(FuelTransaction.batch_id == batch.id))
                await cleanup.execute(
                    delete(FuelSourceControl).where(FuelSourceControl.batch_id == batch.id)
                )
                await cleanup.execute(delete(FuelSourceBatch).where(FuelSourceBatch.id == batch.id))
            await cleanup.execute(delete(FuelNationwide).where(FuelNationwide.tenant_id == TENANT_ID, FuelNationwide.import_id == import_id))
            await cleanup.execute(delete(FuelNationwideStageRow).where(FuelNationwideStageRow.tenant_id == TENANT_ID))
            await cleanup.commit()

    await engine.dispose()
