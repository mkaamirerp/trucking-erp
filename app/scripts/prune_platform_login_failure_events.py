#!/usr/bin/env python3
"""CLI: prune platform_login_failure_events. Prefer scripts/prune_platform_login_failure_events.sh from EC2."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.services.platform_login_failure_prune import (
    DEFAULT_BATCH_SIZE,
    prune_platform_login_failure_events,
    retention_days_from_env,
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Prune old platform_login_failure_events rows (platform DB).")
    p.add_argument(
        "--days",
        type=int,
        default=None,
        help="Retention in days (default: env PLATFORM_LOGIN_FAILURE_RETENTION_DAYS or 90).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per delete batch (default {DEFAULT_BATCH_SIZE}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count rows that would be deleted; no DELETE.",
    )
    args = p.parse_args()
    days = args.days if args.days is not None else retention_days_from_env()
    result = asyncio.run(
        prune_platform_login_failure_events(
            retention_days=days,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    )
    print(
        f"prune_login_failures dry_run={result.dry_run} retention_days={result.retention_days} "
        f"cutoff_utc={result.cutoff_utc.isoformat()} would_delete={result.would_delete} deleted={result.deleted}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
