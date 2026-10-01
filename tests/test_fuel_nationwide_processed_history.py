"""Nationwide processed Fuel history (permanent fuel_nationwide + FINALIZED batch)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.fuel import FuelNationwide, FuelNationwideImportStage, FuelSourceBatch
from app.routers import fuel as fuel_router
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED
from app.services.fuel_nationwide_review import (
    get_nationwide_completed_basic_projection,
    list_nationwide_completed_history,
    list_nationwide_import_rows_for_review,
    process_nationwide_import_review,
)
from app.services.fuel_nationwide_stage import create_nationwide_import_stage_from_pdf
from app.services.fuel_source_duplicate_gate import sha256_hex
from tests.support.integration_isolation import require_integration_tenant_database_url

REPO = Path(__file__).resolve().parents[1]
NW_PDF = REPO / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"
TENANT_A = 53
TENANT_B = 54
INVOICE = "20250522B-06142026"


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_nationwide_history"))
    except Exception:
        return None


REQUIRES_DB = _tenant_url() is None


def test_nationwide_history_routes_registered() -> None:
    paths = {getattr(r, "path", None) for r in fuel_router.router.routes}
    assert "/fuel/nationwide/history" in paths
    assert "/fuel/nationwide/imports/{import_id}/completed-basic" in paths


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant_pytest URL not configured")
async def test_processed_nationwide_appears_in_completed_history() -> None:
    from tests.test_fuel_nationwide_api_routes import _purge_nationwide_fixture

    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pdf = NW_PDF.read_bytes()
    file_sha = sha256_hex(pdf)
    import_id: uuid.UUID | None = None

    async with session_maker() as session:
        await _purge_nationwide_fixture(session, TENANT_A, file_sha)
        await session.commit()

    async with session_maker() as session:
        before = await list_nationwide_completed_history(session, tenant_id=TENANT_A)
        assert not any(h.get("invoice_number") == INVOICE for h in before)

    async with session_maker() as session:
        import_id, *_ = await create_nationwide_import_stage_from_pdf(
            session,
            tenant_id=TENANT_A,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="nationwide_fuel.pdf",
            uploaded_by="test",
        )
        await process_nationwide_import_review(
            session,
            tenant_id=TENANT_A,
            import_id=import_id,
            reviewed_by="test",
            tenant_slug="pytest",
        )
        await session.commit()

    async with session_maker() as session:
        history = await list_nationwide_completed_history(session, tenant_id=TENANT_A)
        match = next((h for h in history if h.get("invoice_number") == INVOICE), None)
        assert match is not None
        assert match["import_id"] == str(import_id)
        assert match["transaction_count"] == 12
        assert match["control_count"] == 14
        assert match["usd_transaction_total"] == "5197.67"
        assert match["usd_provider_control"] == "5197.69"
        assert match["cad_transaction_total"] == "1263.85"

        detail = await get_nationwide_completed_basic_projection(
            session, tenant_id=TENANT_A, import_id=import_id
        )
        rows = await list_nationwide_import_rows_for_review(
            session, tenant_id=TENANT_A, import_id=import_id
        )
        assert rows is not None
        assert all("field_corrections" in r for r in rows)
        stage = await session.scalar(
            select(FuelNationwideImportStage).where(
                FuelNationwideImportStage.tenant_id == TENANT_A,
                FuelNationwideImportStage.stage_id == import_id,
            )
        )
        assert stage is None
        perm = await session.scalar(
            select(FuelNationwide).where(
                FuelNationwide.tenant_id == TENANT_A,
                FuelNationwide.import_id == import_id,
                FuelNationwide.row_type == "HEADER",
            )
        )
        assert perm is not None
        detail_rows = await list_nationwide_import_rows_for_review(
            session, tenant_id=TENANT_A, import_id=import_id
        )
        assert detail_rows is not None
        assert sum(1 for r in detail_rows if r.get("row_type") == "TRANSACTION") == 12
        assert sum(1 for r in detail_rows if r.get("row_type") == "CONTROL") == 14
        txns = [r for r in detail_rows if r.get("row_type") == "TRANSACTION"]
        assert txns[0].get("product") in ("DIESEL", "REEFER", "SCALE")
        batch = await session.scalar(
            select(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.source_import_ref == str(import_id),
                FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            )
        )
        assert batch is not None
        assert detail["usd_transaction_total"] == "5197.67"
        assert detail["usd_provider_control"] == "5197.69"

    async with session_maker() as cleanup:
        if import_id:
            await _purge_nationwide_fixture(cleanup, TENANT_A, file_sha)
            await cleanup.commit()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant_pytest URL not configured")
async def test_tenant_b_cannot_read_tenant_a_processed_nationwide() -> None:
    from tests.test_fuel_nationwide_api_routes import _purge_nationwide_fixture

    url = _tenant_url()
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pdf = NW_PDF.read_bytes()
    file_sha = sha256_hex(pdf)
    import_id: uuid.UUID | None = None

    async with session_maker() as session:
        await _purge_nationwide_fixture(session, TENANT_A, file_sha)
        await session.commit()
        import_id, *_ = await create_nationwide_import_stage_from_pdf(
            session,
            tenant_id=TENANT_A,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="nationwide_fuel.pdf",
            uploaded_by="test",
        )
        await process_nationwide_import_review(
            session,
            tenant_id=TENANT_A,
            import_id=import_id,
            reviewed_by="test",
            tenant_slug="pytest",
        )
        await session.commit()

    async with session_maker() as session_b:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_nationwide_completed_basic_projection(
                session_b, tenant_id=TENANT_B, import_id=import_id
            )
        assert exc.value.status_code == 404

    async with session_maker() as cleanup:
        if import_id:
            await _purge_nationwide_fixture(cleanup, TENANT_A, file_sha)
            await cleanup.commit()
    await engine.dispose()
