"""Nationwide HTTP routes — registration + tenant-scoped integration."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.fuel import (
    FuelNationwide,
    FuelNationwideImportStage,
    FuelSourceControl,
    FuelTransaction,
    FuelSourceBatch,
)
from app.routers import fuel as fuel_router
from app.services.fuel_nationwide_import import import_nationwide_digital_pdf
from app.services.fuel_source_duplicate_gate import sha256_hex
from app.services.fuel_nationwide_review import process_nationwide_import_review
from tests.support.integration_isolation import require_integration_tenant_database_url

REPO = Path(__file__).resolve().parents[1]
NW_PDF = REPO / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"
TENANT_A = 53
TENANT_B = 54


def _fuel_app() -> FastAPI:
    app = FastAPI()
    app.include_router(fuel_router.router, prefix="/api/v1")
    return app


def test_nationwide_api_routes_registered() -> None:
    from app.routers.fuel import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/fuel/nationwide/imports" in paths
    assert "/fuel/nationwide/imports/{import_id}/rows" in paths
    assert "/fuel/nationwide/imports/{import_id}/document" in paths
    assert "/fuel/nationwide/imports/{import_id}/process" in paths


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_nationwide_api"))
    except Exception:
        return None


REQUIRES_DB = _tenant_url() is None


async def _purge_nationwide_fixture(session, tenant_id: int, file_sha: str) -> None:
    import_ids = (
        await session.execute(
            select(FuelNationwide.import_id).where(
                FuelNationwide.tenant_id == tenant_id,
                FuelNationwide.source_file_sha256 == file_sha,
            )
        )
    ).scalars().all()
    for import_id in set(import_ids):
        batch = await session.scalar(
            select(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == tenant_id,
                FuelSourceBatch.source_import_ref == str(import_id),
            )
        )
        if batch:
            await session.execute(delete(FuelTransaction).where(FuelTransaction.batch_id == batch.id))
            await session.execute(delete(FuelSourceControl).where(FuelSourceControl.batch_id == batch.id))
            await session.execute(delete(FuelSourceBatch).where(FuelSourceBatch.id == batch.id))
    await session.execute(
        delete(FuelNationwide).where(
            FuelNationwide.tenant_id == tenant_id,
            FuelNationwide.source_file_sha256 == file_sha,
        )
    )
    await session.execute(
        delete(FuelNationwideImportStage).where(
            FuelNationwideImportStage.tenant_id == tenant_id,
            FuelNationwideImportStage.source_file_sha256 == file_sha,
        )
    )


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant_pytest URL not configured")
async def test_tenant_b_cannot_read_tenant_a_stage() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pdf = NW_PDF.read_bytes()
    stage_id: uuid.UUID | None = None

    file_sha = sha256_hex(pdf)
    async with session_maker() as session:
        await _purge_nationwide_fixture(session, TENANT_A, file_sha)
        await session.commit()
        stage_id, *_ = await import_nationwide_digital_pdf(
            session,
            tenant_id=TENANT_A,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="nationwide.pdf",
            uploaded_by="test",
        )

    async with session_maker() as session_b:
        from app.services.fuel_nationwide_review import list_nationwide_import_rows_for_review

        rows = await list_nationwide_import_rows_for_review(
            session_b, tenant_id=TENANT_B, import_id=stage_id
        )
        assert rows is None

    async with session_maker() as cleanup:
        if stage_id:
            await cleanup.execute(
                delete(FuelNationwideImportStage).where(
                    FuelNationwideImportStage.tenant_id == TENANT_A,
                    FuelNationwideImportStage.stage_id == stage_id,
                )
            )
            await cleanup.commit()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant_pytest URL not configured")
async def test_process_success_twelve_canonical_transactions() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = _tenant_url()
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pdf = NW_PDF.read_bytes()
    file_sha = sha256_hex(pdf)
    stage_id: uuid.UUID | None = None

    async with session_maker() as session:
        await _purge_nationwide_fixture(session, TENANT_A, file_sha)
        await session.commit()

    async with session_maker() as session:
        stage_id, *_ = await import_nationwide_digital_pdf(
            session,
            tenant_id=TENANT_A,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="nationwide.pdf",
            uploaded_by="test",
        )
        await process_nationwide_import_review(
            session,
            tenant_id=TENANT_A,
            import_id=stage_id,
            reviewed_by="test",
            tenant_slug="pytest",
        )
        batch = await session.scalar(
            select(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.source_import_ref == str(stage_id),
            )
        )
        assert batch is not None
        count = await session.scalar(
            select(func.count()).select_from(FuelTransaction).where(
                FuelTransaction.tenant_id == TENANT_A,
                FuelTransaction.batch_id == batch.id,
            )
        )
        assert count == 12

    async with session_maker() as cleanup:
        if stage_id:
            await _purge_nationwide_fixture(cleanup, TENANT_A, file_sha)
            await cleanup.commit()
    await engine.dispose()
