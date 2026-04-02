"""
Safe cleanup of old OTP tokens and onboarding drafts (platform DB).

- OTP tokens: delete where created_at < now_utc - OTP_RETENTION_DAYS (default 30).
- Drafts: delete where created_at < now_utc - DRAFT_RETENTION_DAYS (default 14)
  AND status IN ('PENDING','STALE','FAILED') AND tenant_id IS NULL.
  COMPLETED (tenant-linked) drafts are never deleted by this job.

Run: python -m app.scripts.cleanup_onboarding
Env: DATABASE_URL (platform), OTP_RETENTION_DAYS, DRAFT_RETENTION_DAYS, CLEANUP_DRY_RUN.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.platform import OnboardingStatus, PlatformOnboardingPayload, PlatformOTPToken

# Policy constants (override via env)
OTP_RETENTION_DAYS = int(os.getenv("OTP_RETENTION_DAYS", "30"))
DRAFT_RETENTION_DAYS = int(os.getenv("DRAFT_RETENTION_DAYS", "14"))

OTP_BATCH_SIZE = 5000
DRAFT_BATCH_SIZE = 1000


def _dry_run() -> bool:
    v = (os.getenv("CLEANUP_DRY_RUN", "true") or "true").strip().lower()
    return v in ("true", "1", "yes")


async def _delete_otp_batch(session: AsyncSession, cutoff: datetime, dry_run: bool) -> int:
    """Select up to OTP_BATCH_SIZE ids with created_at < cutoff; delete them. Returns count deleted."""
    subq = (
        select(PlatformOTPToken.id)
        .where(PlatformOTPToken.created_at < cutoff)
        .limit(OTP_BATCH_SIZE)
    )
    result = await session.execute(subq)
    ids = [row[0] for row in result.all()]
    if not ids:
        return 0
    if not dry_run:
        await session.execute(delete(PlatformOTPToken).where(PlatformOTPToken.id.in_(ids)))
        await session.commit()
    return len(ids)


async def _delete_draft_batch(session: AsyncSession, cutoff: datetime, dry_run: bool) -> int:
    """Select up to DRAFT_BATCH_SIZE draft ids (old, status PENDING/STALE/FAILED, tenant_id IS NULL); delete them."""
    statuses = (OnboardingStatus.PENDING.value, OnboardingStatus.STALE.value, OnboardingStatus.FAILED.value)
    subq = (
        select(PlatformOnboardingPayload.id)
        .where(PlatformOnboardingPayload.created_at < cutoff)
        .where(PlatformOnboardingPayload.status.in_(statuses))
        .where(PlatformOnboardingPayload.tenant_id.is_(None))
        .limit(DRAFT_BATCH_SIZE)
    )
    result = await session.execute(subq)
    ids = [row[0] for row in result.all()]
    if not ids:
        return 0
    if not dry_run:
        await session.execute(delete(PlatformOnboardingPayload).where(PlatformOnboardingPayload.id.in_(ids)))
        await session.commit()
    return len(ids)


async def run_cleanup() -> int:
    now = datetime.now(timezone.utc)
    otp_cutoff = now - timedelta(days=OTP_RETENTION_DAYS)
    draft_cutoff = now - timedelta(days=DRAFT_RETENTION_DAYS)
    dry_run = _dry_run()

    print(f"Cleanup onboarding (dry_run={dry_run})")
    print(f"  OTP cutoff: created_at < {otp_cutoff.isoformat()} ({OTP_RETENTION_DAYS} days)")
    print(f"  Draft cutoff: created_at < {draft_cutoff.isoformat()} ({DRAFT_RETENTION_DAYS} days)")
    print(f"  Draft filter: status IN (PENDING, STALE, FAILED), tenant_id IS NULL")
    if dry_run:
        print("  [DRY RUN] No rows will be deleted.")

    total_otp = 0
    total_drafts = 0

    async with AsyncSessionLocal() as session:
        # Delete OTP first (avoids orphan tokens; FK to payload is ON DELETE SET NULL)
        while True:
            n = await _delete_otp_batch(session, otp_cutoff, dry_run)
            total_otp += n
            if n > 0:
                print(f"  OTP: {'would delete' if dry_run else 'deleted'} {n} (total {total_otp})")
            if n < OTP_BATCH_SIZE:
                break

        # Delete old drafts (no tenant link, non-completed only)
        while True:
            n = await _delete_draft_batch(session, draft_cutoff, dry_run)
            total_drafts += n
            if n > 0:
                print(f"  Drafts: {'would delete' if dry_run else 'deleted'} {n} (total {total_drafts})")
            if n < DRAFT_BATCH_SIZE:
                break

    print(f"Done. OTP: {total_otp}, Drafts: {total_drafts}")
    return 0


def main() -> int:
    try:
        return asyncio.run(run_cleanup())
    except Exception as e:
        print(f"Cleanup failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
