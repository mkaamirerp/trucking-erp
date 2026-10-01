"""Authoritative Fuel home dashboard counts (tenant-scoped, no list caps)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelBvd, FuelBvdImportStage, FuelSourceBatch
from app.services.fuel_bvd_canonical_projection import BVD_VENDOR
from app.services.fuel_nationwide_canonical_projection import NATIONWIDE_VENDOR
from app.services.fuel_bvd_review import BVD_REVIEW_IN_PROGRESS, BVD_REVIEW_PENDING
from app.services.fuel_bvd_stage import STAGE_STATUS_ACTIVE
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED

PROCESSED_LOOKBACK_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def count_needs_review(db: AsyncSession, *, tenant_id: int) -> int:
    """Unique imports requiring operator action before Process (current BVD + legacy permanent)."""
    now = _utcnow()
    staged = await db.scalar(
        select(func.count())
        .select_from(FuelBvdImportStage)
        .where(
            FuelBvdImportStage.tenant_id == tenant_id,
            FuelBvdImportStage.status == STAGE_STATUS_ACTIVE,
            FuelBvdImportStage.expires_at > now,
        )
    )
    legacy_open = await db.scalar(
        select(func.count(func.distinct(FuelBvd.import_id)))
        .select_from(FuelBvd)
        .where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.row_type == "HEADER",
            FuelBvd.review_status.in_((BVD_REVIEW_PENDING, BVD_REVIEW_IN_PROGRESS)),
        )
    )
    return int(staged or 0) + int(legacy_open or 0)


async def count_processed_last_7_days(db: AsyncSession, *, tenant_id: int) -> int:
    """Fuel imports with canonical batch FINALIZED in the rolling 7-day window (finalized_at only)."""
    cutoff = _utcnow() - timedelta(days=PROCESSED_LOOKBACK_DAYS)
    count = await db.scalar(
        select(func.count(func.distinct(FuelSourceBatch.source_import_ref)))
        .select_from(FuelSourceBatch)
        .where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.provider_code.in_((BVD_VENDOR, NATIONWIDE_VENDOR)),
            FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            FuelSourceBatch.finalized_at.isnot(None),
            FuelSourceBatch.finalized_at >= cutoff,
            FuelSourceBatch.source_import_ref.isnot(None),
        )
    )
    return int(count or 0)


async def get_fuel_dashboard_stats(db: AsyncSession, *, tenant_id: int) -> dict[str, Any]:
    return {
        "needs_review_count": await count_needs_review(db, tenant_id=tenant_id),
        "processed_last_7_days_count": await count_processed_last_7_days(db, tenant_id=tenant_id),
    }
