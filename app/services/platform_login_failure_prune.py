"""
Prune old rows from platform_login_failure_events (platform DB only).

Run periodically via scripts/prune_platform_login_failure_events.sh (e.g. daily cron on the host).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformLoginFailureEvent

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90
DEFAULT_BATCH_SIZE = 5000


@dataclass(frozen=True)
class PruneResult:
    would_delete: int
    deleted: int
    cutoff_utc: datetime
    retention_days: int
    dry_run: bool


async def prune_platform_login_failure_events(
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> PruneResult:
    """
    Delete events with created_at strictly before (now_utc - retention_days).

    Uses batched deletes by primary key to limit lock duration and WAL spikes.
    """
    if retention_days < 1:
        raise ValueError("retention_days must be >= 1")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with AsyncSessionLocal() as session:
        count_q = await session.scalar(
            select(func.count()).select_from(PlatformLoginFailureEvent).where(
                PlatformLoginFailureEvent.created_at < cutoff
            )
        )
        to_remove = int(count_q or 0)
        if dry_run or to_remove == 0:
            if dry_run:
                logger.info(
                    "platform_login_failure_prune dry_run would_delete=%s retention_days=%s cutoff=%s",
                    to_remove,
                    retention_days,
                    cutoff.isoformat(),
                )
            return PruneResult(
                would_delete=to_remove,
                deleted=0,
                cutoff_utc=cutoff,
                retention_days=retention_days,
                dry_run=dry_run,
            )

        deleted_total = 0
        while True:
            ids = (
                await session.scalars(
                    select(PlatformLoginFailureEvent.id)
                    .where(PlatformLoginFailureEvent.created_at < cutoff)
                    .order_by(PlatformLoginFailureEvent.id)
                    .limit(batch_size)
                )
            ).all()
            if not ids:
                break
            await session.execute(
                delete(PlatformLoginFailureEvent).where(PlatformLoginFailureEvent.id.in_(ids))
            )
            await session.commit()
            deleted_total += len(ids)
            logger.info(
                "platform_login_failure_prune batch deleted=%s total_so_far=%s cutoff=%s",
                len(ids),
                deleted_total,
                cutoff.isoformat(),
            )

        logger.info(
            "platform_login_failure_prune complete deleted_total=%s retention_days=%s",
            deleted_total,
            retention_days,
        )
        return PruneResult(
            would_delete=to_remove,
            deleted=deleted_total,
            cutoff_utc=cutoff,
            retention_days=retention_days,
            dry_run=False,
        )


def retention_days_from_env() -> int:
    raw = os.environ.get("PLATFORM_LOGIN_FAILURE_RETENTION_DAYS", "").strip()
    if not raw:
        return DEFAULT_RETENTION_DAYS
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(
            "PLATFORM_LOGIN_FAILURE_RETENTION_DAYS must be an integer number of days"
        ) from exc
    if n < 1:
        raise ValueError("PLATFORM_LOGIN_FAILURE_RETENTION_DAYS must be >= 1")
    return n
