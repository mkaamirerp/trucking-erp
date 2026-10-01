"""Canonical processed Fuel read path (Phase 2)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.fuel import FuelSourceBatch, FuelTransaction
from app.routers import fuel as fuel_router
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED
from app.services.fuel_nationwide_review import process_nationwide_import_review
from app.services.fuel_nationwide_stage import create_nationwide_import_stage_from_pdf
from app.services.fuel_processed_read import get_processed_fuel_batch, list_processed_fuel
from app.services.fuel_source_duplicate_gate import sha256_hex
from tests.support.integration_isolation import require_integration_tenant_database_url

REPO = Path(__file__).resolve().parents[1]
NW_PDF = REPO / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"

TENANT_A = 53
TENANT_B = 54
DEMO_INVOICE = "20250522B-06142026"
TEST_PROVIDER = "TEST_PROVIDER"


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_processed_read"))
    except Exception:
        return None


REQUIRES_DB = _tenant_url() is None


def test_processed_routes_registered() -> None:
    paths = {getattr(r, "path", None) for r in fuel_router.router.routes}
    assert "/fuel/processed" in paths
    assert "/fuel/processed/{batch_id}" in paths


def test_processed_read_module_has_no_provider_history_imports() -> None:
    import inspect

    import app.services.fuel_processed_read as mod

    source = inspect.getsource(mod)
    assert "list_bvd_completed_history" not in source
    assert "list_nationwide_completed_history" not in source
    assert "if provider_code ==" not in source.replace(" ", "")


@pytest.mark.asyncio
async def test_test_provider_batch_appears_without_provider_history_code() -> None:
    """Architecture gate: TEST_PROVIDER uses canonical list only."""
    from sqlalchemy.ext.asyncio import AsyncSession

    session = AsyncSession  # type hint only
    mock_batch = FuelSourceBatch(
        id=99_001,
        tenant_id=TENANT_A,
        provider_code=TEST_PROVIDER,
        source_type="PDF",
        status=BATCH_STATUS_FINALIZED,
        finalized_at=datetime.now(timezone.utc),
        invoice_number="TEST-INV-1",
        source_import_ref=str(uuid.uuid4()),
    )
    mock_txn = FuelTransaction(
        id=1,
        tenant_id=TENANT_A,
        batch_id=mock_batch.id,
        source_row_order=1,
        source_vendor=TEST_PROVIDER,
        provider_event_type="PURCHASE",
        transaction_datetime_source="2025-01-01",
        transaction_timezone_source="UNKNOWN",
        currency="USD",
        total_amount=Decimal("10.00"),
        provider_raw={},
    )

    class _ScalarResult:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _FakeSession:
        def __init__(self):
            self._step = 0

        async def scalars(self, stmt):
            self._step += 1
            if self._step == 1:
                return _ScalarResult([mock_batch])
            if self._step == 2:
                return _ScalarResult([mock_txn])
            return _ScalarResult([])

    out = await list_processed_fuel(_FakeSession(), tenant_id=TENANT_A)
    assert len(out) == 1
    assert out[0]["provider_code"] == TEST_PROVIDER
    assert out[0]["transaction_count"] == 1


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant DB required")
async def test_list_processed_fuel_tenant_isolation_and_providers() -> None:
    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        tenant_a = await list_processed_fuel(session, tenant_id=TENANT_A)
        tenant_b = await list_processed_fuel(session, tenant_id=TENANT_B)
        codes_a = {row["provider_code"] for row in tenant_a}
        codes_b = {row["provider_code"] for row in tenant_b}
        assert "BVD" in codes_a or "NATIONWIDE" in codes_a
        for row in tenant_b:
            assert row["batch_id"] not in {r["batch_id"] for r in tenant_a} or not tenant_a

    async with session_maker() as session:
        for row in tenant_a:
            shape = set(row.keys())
            assert "batch_id" in shape
            assert "provider_code" in shape
            assert "currency_totals" in shape
            assert "transaction_count" in shape


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant DB required")
async def test_nationwide_demo_batch_8_canonical_totals() -> None:
    """Process fixture Nationwide invoice on tenant_pytest; assert canonical processed read totals."""
    from tests.test_fuel_nationwide_api_routes import _purge_nationwide_fixture

    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pdf = NW_PDF.read_bytes()
    file_sha = sha256_hex(pdf)
    import_id: uuid.UUID | None = None
    batch_id: int | None = None

    async with session_maker() as session:
        await _purge_nationwide_fixture(session, TENANT_A, file_sha)
        await session.commit()

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
        batch = await session.scalar(
            select(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.source_import_ref == str(import_id),
                FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            )
        )
        assert batch is not None
        batch_id = int(batch.id)
        await session.commit()

    async with session_maker() as session:
        items = await list_processed_fuel(session, tenant_id=TENANT_A)
        nw = next((x for x in items if x.get("batch_id") == batch_id), None)
        assert nw is not None
        assert nw["invoice_number"] == DEMO_INVOICE
        assert nw["provider_code"] == "NATIONWIDE"
        assert nw["source_import_ref"] == str(import_id)
        assert nw["batch_id"] == batch_id
        assert nw["transaction_count"] == 12
        assert nw["control_count"] == 14
        assert Decimal(nw["cad_transaction_total"]) == Decimal("1263.85")
        assert Decimal(nw["usd_transaction_total"]) == Decimal("5197.67")
        assert Decimal(nw["usd_provider_control"]) == Decimal("5197.69")
        assert nw["currency"] is None or nw["currency"] in ("CAD", "USD")
        if nw["currency"] is None:
            assert nw["total_amount"] in ("", None)

        detail = await get_processed_fuel_batch(session, tenant_id=TENANT_A, batch_id=batch_id)
        assert detail["source_import_ref"] == str(import_id)
        assert detail["batch_id"] == batch_id
        assert len(detail["canonical_transactions"]) == 12

    async with session_maker() as cleanup:
        if import_id:
            await _purge_nationwide_fixture(cleanup, TENANT_A, file_sha)
            await cleanup.commit()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant DB required")
async def test_get_processed_fuel_batch_404_other_tenant() -> None:
    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        batch_id = await session.scalar(
            select(FuelSourceBatch.id).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            ).limit(1)
        )
        if batch_id is None:
            pytest.skip("no finalized batch on tenant A")

    async with session_maker() as session:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_processed_fuel_batch(session, tenant_id=TENANT_B, batch_id=int(batch_id))
        assert exc.value.status_code == 404


