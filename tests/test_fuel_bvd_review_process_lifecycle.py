"""BVD review → Process lifecycle on synthetic seeded rows (integration DB only)."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.fuel import FuelBvd, FuelBvdFieldCorrection
from app.services.fuel_bvd_effective import build_effective_bvd_row
from app.services.fuel_bvd_import import BVD_SOURCE_FIELD_NAMES
from app.services.fuel_bvd_review import (
    BVD_REVIEW_IN_PROGRESS,
    BVD_REVIEW_SOURCE_COMPLETE,
    get_bvd_source_reconciliation_report,
    list_bvd_import_rows_for_review,
    process_bvd_import_review,
    reconcile_bvd_import_review_rows,
    save_bvd_import_review,
)
from app.core.integration_db_guard import assert_tenant_database_url_allowed
from app.models.platform import PlatformTenant
from tests.test_fuel_bvd_effective_review import _df_to_s_scale_fixture


def _tenant_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    try:
        os.environ.setdefault("ENVIRONMENT", "test")
        assert_tenant_database_url_allowed(raw, context="fuel_bvd_process_lifecycle")
        return to_async_pg_url(raw.strip())
    except Exception:
        return None


REQUIRES_TENANT_DB = _tenant_url() is None


async def _resolve_pytest_tenant_id() -> int:
    override = os.environ.get("FUEL_BVD_LIFECYCLE_TENANT_ID")
    if override:
        return int(override)
    platform_url = os.environ.get("DATABASE_URL") or os.environ.get("ALEMBIC_PLATFORM_DATABASE_URL")
    if not platform_url:
        pytest.fail("DATABASE_URL required to resolve pytest tenant id")
    platform_engine = create_async_engine(to_async_pg_url(platform_url), pool_pre_ping=True)
    try:
        async with AsyncSession(platform_engine, expire_on_commit=False) as platform_session:
            tid = await platform_session.scalar(
                select(PlatformTenant.id).where(PlatformTenant.slug == "pytest").limit(1)
            )
            if tid is None:
                pytest.fail("platform tenant slug=pytest not found")
            return int(tid)
    finally:
        await platform_engine.dispose()


async def _seed_df_to_s_synthetic_import(
    session: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> int:
    """Insert IN_REVIEW synthetic import; return fuel_bvd id of SCALE-1 transaction."""
    now = datetime.now(timezone.utc)
    file_sha = hashlib.sha256(f"synthetic-lifecycle-{import_id}".encode()).hexdigest()
    invoice = f"SYN-LC-{import_id.hex[:12]}"
    txn_fuel_bvd_id: int | None = None

    for order, spec in enumerate(_df_to_s_scale_fixture(), start=1):
        row = FuelBvd(
            tenant_id=tenant_id,
            import_id=import_id,
            row_type=spec["row_type"],
            review_status=BVD_REVIEW_IN_PROGRESS,
            source_row_number=order,
            source_page=1,
            source_file_name=f"{invoice}.pdf",
            source_file_sha256=file_sha,
            source_storage_ref=f"pytest/synthetic/{import_id}.pdf",
            uploaded_at=now,
            uploaded_by="pytest_lifecycle",
            processing_started_at=now,
            processing_completed_at=now,
            processing_duration_ms=1,
            processed_by="pytest_lifecycle",
            parser_version="pytest-synthetic",
            parse_status="SUCCESS",
        )
        if spec.get("row_type") == "HEADER":
            row.invoice_number = invoice
        for name in BVD_SOURCE_FIELD_NAMES:
            if name in spec:
                setattr(row, name, spec[name])
        session.add(row)
        await session.flush()
        if spec.get("auth_code") == "SCALE-1":
            txn_fuel_bvd_id = row.id

    await session.commit()
    assert txn_fuel_bvd_id is not None
    return txn_fuel_bvd_id


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL tenant_pytest required")
async def test_df_to_s_synthetic_import_full_process_lifecycle() -> None:
    """Parser DF → reviewed S → reconcile PASS → Process → lock; raw DF preserved."""
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: FuelBvd.__table__.create(sync, checkfirst=True))
        await conn.run_sync(lambda sync: FuelBvdFieldCorrection.__table__.create(sync, checkfirst=True))

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import_id = uuid.uuid4()

    async with session_factory() as session:
        tenant_id = await _resolve_pytest_tenant_id()

        txn_row_id = await _seed_df_to_s_synthetic_import(
            session, tenant_id=tenant_id, import_id=import_id
        )

        rows_before = await list_bvd_import_rows_for_review(
            session, tenant_id=tenant_id, import_id=import_id
        )
        recon_before = await get_bvd_source_reconciliation_report(
            session, tenant_id=tenant_id, import_id=import_id
        )
        assert recon_before["passed"] is False

        await save_bvd_import_review(
            session,
            tenant_id=tenant_id,
            import_id=import_id,
            reviewed_by="pytest_lifecycle",
            corrections=[
                {
                    "fuel_bvd_id": txn_row_id,
                    "field_name": "prod",
                    "reviewed_value": "S",
                }
            ],
        )

        rows_mid = await list_bvd_import_rows_for_review(
            session, tenant_id=tenant_id, import_id=import_id
        )
        txn_mid = next(r for r in rows_mid if r.get("auth_code") == "SCALE-1")
        assert txn_mid["prod"] == "DF"
        assert txn_mid["field_corrections"]["prod"]["reviewed_value"] == "S"
        assert build_effective_bvd_row(txn_mid)["prod"] == "S"

        recon_after = await get_bvd_source_reconciliation_report(
            session, tenant_id=tenant_id, import_id=import_id
        )
        assert recon_after["passed"] is True
        assert reconcile_bvd_import_review_rows(rows_mid).passed is True

        summary = await process_bvd_import_review(
            session,
            tenant_id=tenant_id,
            import_id=import_id,
            reviewed_by="pytest_lifecycle",
        )
        assert summary["review_status"] == BVD_REVIEW_SOURCE_COMPLETE

        rows_final = await list_bvd_import_rows_for_review(
            session, tenant_id=tenant_id, import_id=import_id
        )
        txn_final = next(r for r in rows_final if r.get("auth_code") == "SCALE-1")
        assert txn_final["prod"] == "DF"
        assert txn_final["field_corrections"]["prod"]["reviewed_value"] == "S"
        assert build_effective_bvd_row(txn_final)["prod"] == "S"
        assert txn_final.get("review_status") == BVD_REVIEW_SOURCE_COMPLETE

        corr_count_before = await session.scalar(
            select(func.count())
            .select_from(FuelBvdFieldCorrection)
            .where(
                FuelBvdFieldCorrection.tenant_id == tenant_id,
                FuelBvdFieldCorrection.import_id == import_id,
            )
        )
        assert int(corr_count_before or 0) == 1

        with pytest.raises(HTTPException) as locked_exc:
            await save_bvd_import_review(
                session,
                tenant_id=tenant_id,
                import_id=import_id,
                reviewed_by="pytest_lifecycle",
                corrections=[
                    {
                        "fuel_bvd_id": txn_row_id,
                        "field_name": "prod",
                        "reviewed_value": "DF",
                    }
                ],
            )
        assert locked_exc.value.detail["code"] == "BVD_REVIEW_LOCKED"

        corr_count_after = await session.scalar(
            select(func.count())
            .select_from(FuelBvdFieldCorrection)
            .where(
                FuelBvdFieldCorrection.tenant_id == tenant_id,
                FuelBvdFieldCorrection.import_id == import_id,
            )
        )
        assert int(corr_count_after or 0) == int(corr_count_before or 0)

        raw_prod = await session.scalar(
            select(FuelBvd.prod).where(
                FuelBvd.tenant_id == tenant_id,
                FuelBvd.id == txn_row_id,
            )
        )
        assert raw_prod == "DF"

        await session.execute(
            FuelBvdFieldCorrection.__table__.delete().where(
                FuelBvdFieldCorrection.tenant_id == tenant_id,
                FuelBvdFieldCorrection.import_id == import_id,
            )
        )
        await session.execute(
            FuelBvd.__table__.delete().where(
                FuelBvd.tenant_id == tenant_id,
                FuelBvd.import_id == import_id,
            )
        )
        await session.commit()

    await engine.dispose()
