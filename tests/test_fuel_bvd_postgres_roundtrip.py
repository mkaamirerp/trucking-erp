"""BVD Implementation 1 — isolated PostgreSQL round-trip (tenant_pytest only)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

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
from app.services.fuel_source_duplicate_gate import sha256_hex
from app.services.fuel_bvd_import import BVD_SOURCE_FIELD_NAMES, import_bvd_digital_pdf
from app.services.fuel_bvd_review import list_bvd_import_rows_for_review, process_bvd_import_review
from tests.support.integration_isolation import require_integration_tenant_database_url

REPO = Path(__file__).resolve().parents[1]
BVD_PDF = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"
GOLDEN = REPO / "tests" / "fixtures" / "fuel_bvd_972201_expected.json"

INTEGRATION_TENANT_ID = 53


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_bvd_postgres_roundtrip"))
    except Exception:
        return None


REQUIRES_TENANT_DB = _tenant_url() is None


def _golden_rows() -> list[dict]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["rows"]


async def _safe_table_row_count(session: AsyncSession, table_name: str) -> int:
    """Count rows when the table exists; isolated tenant_pytest may not have Fuel segment tables."""
    reg = await session.scalar(text("SELECT to_regclass(:name)"), {"name": table_name})
    if reg is None:
        return 0
    result = await session.execute(text(f"SELECT count(*) FROM {table_name}"))
    return int(result.scalar_one())


def _db_shaped_from_orm(rows: list[FuelBvd]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        item = {
            "source_row_number": row.source_row_number,
            "row_type": row.row_type,
            "source_page": row.source_page,
        }
        for name in BVD_SOURCE_FIELD_NAMES:
            val = getattr(row, name)
            if val is not None:
                item[name] = val
        out.append(item)
    return out


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL tenant_pytest required")
async def test_bvd_import_postgres_roundtrip_matches_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)

    async with engine.begin() as conn:
        for table in (
            FuelBvd.__table__,
            FuelBvdFieldCorrection.__table__,
            FuelBvdImportStage.__table__,
            FuelBvdStageRow.__table__,
            FuelBvdStageFieldCorrection.__table__,
        ):
            await conn.run_sync(lambda sync, t=table: t.create(sync, checkfirst=True))

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=True)

    async def _fake_stage_save(tenant_slug: str, stage_id: str, body: bytes, **kwargs):
        from app.core.storage import StoredFile
        from app.services.fuel_source_duplicate_gate import sha256_hex

        key = f"pytest/fuel_bvd_stage/stage/{stage_id}/file.pdf"
        return StoredFile(key, kwargs.get("filename_hint"), "application/pdf", len(body), sha256_hex(body))

    async def _fake_perm_save(tenant_slug: str, import_id: str, body: bytes, **kwargs):
        from app.core.storage import StoredFile
        from app.services.fuel_source_duplicate_gate import sha256_hex

        key = f"pytest/fuel_bvd/import/{import_id}/file.pdf"
        return StoredFile(key, kwargs.get("filename_hint"), "application/pdf", len(body), sha256_hex(body))

    monkeypatch.setattr("app.services.fuel_bvd_stage.save_fuel_bvd_stage_bytes", _fake_stage_save)
    monkeypatch.setattr("app.services.fuel_bvd_stage.purge_expired_stages", AsyncMock(return_value=0))
    monkeypatch.setattr("app.services.fuel_bvd_stage.save_fuel_bvd_import_bytes", _fake_perm_save)
    monkeypatch.setattr(
        "app.services.fuel_bvd_stage.get_storage",
        lambda: type("S", (), {"read_bytes": lambda *a, **k: BVD_PDF.read_bytes()})(),
    )

    import_id: uuid.UUID
    pdf_bytes = BVD_PDF.read_bytes()
    file_sha = sha256_hex(pdf_bytes)
    async with session_factory() as session:
        batch_ids = list(
            (
                await session.scalars(
                    select(FuelSourceBatch.id).where(
                        FuelSourceBatch.tenant_id == INTEGRATION_TENANT_ID,
                        FuelSourceBatch.source_hash == file_sha,
                    )
                )
            ).all()
        )
        if batch_ids:
            await session.execute(
                delete(FuelTransaction).where(
                    FuelTransaction.tenant_id == INTEGRATION_TENANT_ID,
                    FuelTransaction.batch_id.in_(batch_ids),
                )
            )
            await session.execute(
                delete(FuelSourceControl).where(
                    FuelSourceControl.tenant_id == INTEGRATION_TENANT_ID,
                    FuelSourceControl.batch_id.in_(batch_ids),
                )
            )
            await session.execute(
                delete(FuelSourceBatch).where(
                    FuelSourceBatch.tenant_id == INTEGRATION_TENANT_ID,
                    FuelSourceBatch.id.in_(batch_ids),
                )
            )
        await session.execute(
            delete(FuelBvd).where(
                FuelBvd.tenant_id == INTEGRATION_TENANT_ID,
                FuelBvd.source_file_sha256 == file_sha,
            )
        )
        await session.execute(
            delete(FuelBvdImportStage).where(
                FuelBvdImportStage.tenant_id == INTEGRATION_TENANT_ID,
                FuelBvdImportStage.source_file_sha256 == file_sha,
            )
        )
        await session.commit()

    async with session_factory() as session:
        txn_before = await _safe_table_row_count(session, FuelTransaction.__tablename__)
        ctrl_before = await _safe_table_row_count(session, FuelSourceControl.__tablename__)
        bvd_before = await _safe_table_row_count(session, FuelBvd.__tablename__)
        import_id, count, status = await import_bvd_digital_pdf(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            tenant_slug="pytest",
            pdf_bytes=pdf_bytes,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="pytest",
        )
        assert status == "SUCCESS"
        assert count == 24
        bvd_mid = await _safe_table_row_count(session, FuelBvd.__tablename__)
        assert bvd_mid == bvd_before
        txn_after = await _safe_table_row_count(session, FuelTransaction.__tablename__)
        ctrl_after = await _safe_table_row_count(session, FuelSourceControl.__tablename__)
        assert txn_after == txn_before
        assert ctrl_after == ctrl_before

    async with session_factory() as session:
        staged = await list_bvd_import_rows_for_review(
            session, tenant_id=INTEGRATION_TENANT_ID, import_id=import_id
        )
        assert len(staged) == 24
        await process_bvd_import_review(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            import_id=import_id,
            reviewed_by="pytest",
            tenant_slug="pytest",
        )

    async with session_factory() as session:
        from app.services.fuel_bvd_import import list_bvd_import_rows

        loaded = await list_bvd_import_rows(
            session, tenant_id=INTEGRATION_TENANT_ID, import_id=import_id
        )
        assert len(loaded) == 24
        shaped = _db_shaped_from_orm(loaded)
        assert shaped == _golden_rows()
        t1 = next(r for r in shaped if r.get("auth_code") == "A204040667-TA")
        assert t1["pre_tax_amt"] == "1,425.63"
        assert t1["disc_rate"] == "0.0000"
        t2 = next(r for r in shaped if r.get("auth_code") == "A208448597-TA")
        assert t2["unit_number"] == "1104"
        assert t2["transaction_date"] == "2026-07-27 13:38:39"
        assert t2["cur"] == "CN"

    await engine.dispose()
