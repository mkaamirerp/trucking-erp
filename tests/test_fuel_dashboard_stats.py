"""Fuel home dashboard stats — authoritative counts (no list caps)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.fuel import FuelBvd, FuelBvdImportStage, FuelSourceBatch
from app.services.fuel_bvd_canonical_projection import BVD_VENDOR
from app.services.fuel_bvd_review import BVD_REVIEW_IN_PROGRESS, BVD_REVIEW_PENDING, BVD_REVIEW_SOURCE_COMPLETE
from app.services.fuel_bvd_stage import STAGE_STATUS_ACTIVE
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED, BATCH_STATUS_PROCESSING
from app.services.fuel_dashboard_stats import (
    count_needs_review,
    count_processed_last_7_days,
    get_fuel_dashboard_stats,
)
from tests.support.integration_isolation import require_integration_tenant_database_url

# Dedicated tenant_ids for dashboard stats integration (avoid collision with BVD PDF tests on 53).
TENANT_A = 990_001
TENANT_B = 990_002


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_dashboard_stats"))
    except Exception:
        return None


REQUIRES_TENANT_DB = _tenant_url() is None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_get_fuel_dashboard_stats_aggregates_subcounts() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[2, 3, 5])
    out = await get_fuel_dashboard_stats(session, tenant_id=TENANT_A)
    assert out == {"needs_review_count": 5, "processed_last_7_days_count": 5}
    assert session.scalar.await_count == 3


@pytest.mark.asyncio
async def test_count_queries_do_not_use_limit() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=0)

    await count_needs_review(session, tenant_id=TENANT_A)
    await count_processed_last_7_days(session, tenant_id=TENANT_A)

    for call in session.scalar.await_args_list:
        stmt = call.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT" not in compiled.upper()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="integration tenant DB required")
async def test_needs_review_integration_matrix() -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _utcnow()
    stage_active = uuid.uuid4()
    stage_expired = uuid.uuid4()
    legacy_pending = uuid.uuid4()
    legacy_review = uuid.uuid4()
    legacy_done = uuid.uuid4()

    async with factory() as session:
        session.add_all(
            [
                FuelBvdImportStage(
                    stage_id=stage_active,
                    tenant_id=TENANT_A,
                    provider_code="BVD",
                    status=STAGE_STATUS_ACTIVE,
                    expires_at=now + timedelta(hours=2),
                ),
                FuelBvdImportStage(
                    stage_id=stage_expired,
                    tenant_id=TENANT_A,
                    provider_code="BVD",
                    status=STAGE_STATUS_ACTIVE,
                    expires_at=now - timedelta(hours=1),
                ),
                FuelBvdImportStage(
                    stage_id=uuid.uuid4(),
                    tenant_id=TENANT_B,
                    provider_code="BVD",
                    status=STAGE_STATUS_ACTIVE,
                    expires_at=now + timedelta(hours=2),
                ),
            ]
        )
        for import_id, status in [
            (legacy_pending, BVD_REVIEW_PENDING),
            (legacy_review, BVD_REVIEW_IN_PROGRESS),
            (legacy_done, BVD_REVIEW_SOURCE_COMPLETE),
        ]:
            session.add(
                FuelBvd(
                    tenant_id=TENANT_A,
                    import_id=import_id,
                    row_type="HEADER",
                    review_status=status,
                )
            )
            session.add(
                FuelBvd(
                    tenant_id=TENANT_A,
                    import_id=import_id,
                    row_type="TRANSACTION",
                    review_status=status,
                )
            )
        await session.commit()

        assert await count_needs_review(session, tenant_id=TENANT_A) == 3
        assert await count_needs_review(session, tenant_id=TENANT_B) == 1

        await session.execute(
            FuelBvdImportStage.__table__.delete().where(
                FuelBvdImportStage.stage_id.in_([stage_active, stage_expired])
            )
        )
        await session.execute(
            FuelBvd.__table__.delete().where(
                FuelBvd.tenant_id == TENANT_A,
                FuelBvd.import_id.in_([legacy_pending, legacy_review, legacy_done]),
            )
        )
        await session.execute(
            FuelBvdImportStage.__table__.delete().where(FuelBvdImportStage.tenant_id == TENANT_B)
        )
        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="integration tenant DB required")
async def test_processed_last_7_days_uses_finalized_at_only() -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _utcnow()
    recent_ref = str(uuid.uuid4())
    old_ref = str(uuid.uuid4())
    processing_ref = str(uuid.uuid4())
    other_tenant_ref = str(uuid.uuid4())

    async with factory() as session:
        session.add_all(
            [
                FuelSourceBatch(
                    tenant_id=TENANT_A,
                    provider_code=BVD_VENDOR,
                    source_type="PDF",
                    status=BATCH_STATUS_FINALIZED,
                    source_import_ref=recent_ref,
                    finalized_at=now - timedelta(days=2),
                ),
                FuelSourceBatch(
                    tenant_id=TENANT_A,
                    provider_code=BVD_VENDOR,
                    source_type="PDF",
                    status=BATCH_STATUS_FINALIZED,
                    source_import_ref=old_ref,
                    finalized_at=now - timedelta(days=10),
                ),
                FuelSourceBatch(
                    tenant_id=TENANT_A,
                    provider_code=BVD_VENDOR,
                    source_type="PDF",
                    status=BATCH_STATUS_PROCESSING,
                    source_import_ref=processing_ref,
                    finalized_at=None,
                ),
                FuelSourceBatch(
                    tenant_id=TENANT_B,
                    provider_code=BVD_VENDOR,
                    source_type="PDF",
                    status=BATCH_STATUS_FINALIZED,
                    source_import_ref=other_tenant_ref,
                    finalized_at=now - timedelta(days=1),
                ),
            ]
        )
        await session.commit()

        assert await count_processed_last_7_days(session, tenant_id=TENANT_A) == 1
        assert await count_processed_last_7_days(session, tenant_id=TENANT_B) == 1

        legacy_only = uuid.uuid4()
        session.add(
            FuelBvd(
                tenant_id=TENANT_A,
                import_id=legacy_only,
                row_type="HEADER",
                review_status=BVD_REVIEW_SOURCE_COMPLETE,
                reviewed_at=now - timedelta(days=1),
            )
        )
        await session.commit()
        assert await count_processed_last_7_days(session, tenant_id=TENANT_A) == 1

        ids = await session.scalars(
            select(FuelSourceBatch.id).where(
                FuelSourceBatch.tenant_id.in_([TENANT_A, TENANT_B]),
                FuelSourceBatch.source_import_ref.in_(
                    [recent_ref, old_ref, processing_ref, other_tenant_ref]
                ),
            )
        )
        batch_ids = list(ids.all())
        await session.execute(FuelSourceBatch.__table__.delete().where(FuelSourceBatch.id.in_(batch_ids)))
        await session.execute(
            FuelBvd.__table__.delete().where(FuelBvd.tenant_id == TENANT_A, FuelBvd.import_id == legacy_only)
        )
        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="integration tenant DB required")
async def test_processed_count_above_forty_without_cap() -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _utcnow()
    refs = [str(uuid.uuid4()) for _ in range(45)]

    async with factory() as session:
        for ref in refs:
            session.add(
                FuelSourceBatch(
                    tenant_id=TENANT_A,
                    provider_code=BVD_VENDOR,
                    source_type="PDF",
                    status=BATCH_STATUS_FINALIZED,
                    source_import_ref=ref,
                    finalized_at=now - timedelta(hours=12),
                )
            )
        await session.commit()
        assert await count_processed_last_7_days(session, tenant_id=TENANT_A) == 45
        await session.execute(
            FuelSourceBatch.__table__.delete().where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.source_import_ref.in_(refs),
            )
        )
        await session.commit()

    await engine.dispose()
