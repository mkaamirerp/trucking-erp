"""
Renew Gmail users.watch for all tenants whose watch expires within gmail_watch_renew_within_hours.

Run inside API container (same env / DB as production):
  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.renew_gmail_watches'

Env:
  GMAIL_PUBSUB_TOPIC_NAME / settings — required or script no-ops with message.
  GMAIL_WATCH_RENEW_BEFORE_HOURS — optional override for threshold (default: settings.gmail_watch_renew_within_hours).
  RENEW_GMAIL_FORCE=1 — renew every connected Gmail tenant regardless of expiration.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import PlatformTenant
from app.models.tenant_email_account import TenantEmailAccount
from app.services.gmail_watch import register_or_renew_gmail_watch_for_tenant


def _force() -> bool:
    return (os.environ.get("RENEW_GMAIL_FORCE", "") or "").strip().lower() in ("1", "true", "yes")


async def _run() -> int:
    topic = getattr(settings, "gmail_pubsub_topic_name", None)
    if not topic or not str(topic).strip():
        print("GMAIL_PUBSUB_TOPIC_NAME not set; exiting.", file=sys.stderr)
        return 0

    within_env = os.environ.get("GMAIL_WATCH_RENEW_BEFORE_HOURS")
    within = int(within_env) if within_env else max(1, int(getattr(settings, "gmail_watch_renew_within_hours", 48)))
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(hours=within)
    force = _force()

    async with AsyncSessionLocal() as pdb:
        result = await pdb.execute(
            select(PlatformTenant).where(
                PlatformTenant.status == "ACTIVE",
                PlatformTenant.db_status == "READY",
                PlatformTenant.db_name.isnot(None),
            )
        )
        tenants = list(result.scalars().all())

    renewed = 0
    skipped = 0
    failed = 0

    for t in tenants:
        tid = int(t.id)
        try:
            async for tdb in open_tenant_session_by_id(tid):
                acc = await tdb.scalar(
                    select(TenantEmailAccount)
                    .where(
                        TenantEmailAccount.tenant_id == tid,
                        TenantEmailAccount.provider == "gmail",
                    )
                    .limit(1)
                )
                if not acc:
                    break
                exp = acc.gmail_watch_expiration_at
                if not force and exp and exp > threshold:
                    skipped += 1
                    break
                try:
                    await register_or_renew_gmail_watch_for_tenant(tdb, tid, topic_name=str(topic).strip())
                    renewed += 1
                except Exception as exc:
                    print(f"tenant_id={tid} renew failed: {exc}", file=sys.stderr)
                    failed += 1
                break
        except Exception as exc:
            print(f"tenant_id={tid} skipped (db/open): {exc}", file=sys.stderr)
            failed += 1

    print(f"renew_gmail_watches: renewed={renewed} skipped_not_due={skipped} failed={failed} force={force}")
    return 1 if failed else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
