"""One-shot login step-up OTP after admin/platform unlock clears password-fail streak (platform DB)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import PlatformLoginUnlockStepUpPending
from app.services.login_failure_audit import email_fingerprint

logger = logging.getLogger(__name__)


async def set_login_step_up_pending_after_unlock(db: AsyncSession, tenant_id: int, email_norm: str) -> None:
    """Mark tenant+email for mandatory step-up on next successful password (idempotent refresh if already pending)."""
    fp = email_fingerprint(email_norm)
    now = datetime.now(timezone.utc)
    row = await db.scalar(
        select(PlatformLoginUnlockStepUpPending).where(
            PlatformLoginUnlockStepUpPending.tenant_id == int(tenant_id),
            PlatformLoginUnlockStepUpPending.email_fingerprint == fp,
        )
    )
    if row:
        row.created_at = now
    else:
        db.add(
            PlatformLoginUnlockStepUpPending(
                tenant_id=int(tenant_id),
                email_fingerprint=fp,
                created_at=now,
            )
        )
    await db.commit()
    logger.info(
        "event=login_step_up_pending_after_unlock_set tenant_id=%s email_fingerprint=%s",
        int(tenant_id),
        fp,
    )


async def clear_login_step_up_pending_after_successful_step_up(
    db: AsyncSession, tenant_id: int, email_norm: str
) -> None:
    """Remove mandate after OTP step-up consumed and session is about to be issued."""
    fp = email_fingerprint(email_norm)
    await db.execute(
        delete(PlatformLoginUnlockStepUpPending).where(
            PlatformLoginUnlockStepUpPending.tenant_id == int(tenant_id),
            PlatformLoginUnlockStepUpPending.email_fingerprint == fp,
        )
    )
    await db.commit()
    logger.info(
        "event=login_step_up_pending_after_unlock_cleared tenant_id=%s email_fingerprint=%s",
        int(tenant_id),
        fp,
    )


async def login_step_up_pending_after_unlock_exists(db: AsyncSession, tenant_id: int, email_norm: str) -> bool:
    fp = email_fingerprint(email_norm)
    rid = await db.scalar(
        select(PlatformLoginUnlockStepUpPending.id).where(
            PlatformLoginUnlockStepUpPending.tenant_id == int(tenant_id),
            PlatformLoginUnlockStepUpPending.email_fingerprint == fp,
        )
    )
    return rid is not None
