#!/usr/bin/env python3
"""One-time loads.active_trip_id repair from OPEN ACTIVE TripLoad only.

Usage (inside truckerp-api with secrets):

  set -a && . /run/secrets/truckerp.env && set +a
  cd /app
  python -m app.scripts.repair_active_trip_id_pointers --tenant-id 53 --dry-run
  python -m app.scripts.repair_active_trip_id_pointers --tenant-id 53

With --require-demo-audit (default for tenant_id 53), plan must match the
audited category-A set exactly or the script STOPs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.services.load_custody import (
    CustodyBootstrapAnomaly,
    TENANT_DEMO_AUDITED_POINTER_REPAIRS,
    repair_load_active_trip_pointers,
)


def _tenant_url() -> str:
    import os

    raw = os.environ.get("ALEMBIC_TENANT_DATABASE_URL") or os.environ.get("TENANT_DATABASE_URL")
    if not raw:
        raise SystemExit("ALEMBIC_TENANT_DATABASE_URL or TENANT_DATABASE_URL required")
    return to_async_pg_url(raw)


async def _amain(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Repair loads.active_trip_id from OPEN ACTIVE TripLoad")
    p.add_argument("--tenant-id", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--require-demo-audit",
        action="store_true",
        help="Require exact audited plan (auto-enabled for tenant_id 53)",
    )
    p.add_argument(
        "--no-require-demo-audit",
        action="store_true",
        help="Allow any category-A recomputes without the audited six-row plan",
    )
    args = p.parse_args(argv)

    require_audit = args.require_demo_audit or (
        args.tenant_id == 53 and not args.no_require_demo_audit
    )
    expected = TENANT_DEMO_AUDITED_POINTER_REPAIRS if require_audit else None

    engine = create_async_engine(_tenant_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            try:
                summary = await repair_load_active_trip_pointers(
                    session,
                    args.tenant_id,
                    dry_run=args.dry_run,
                    expected_repairs=expected,
                )
            except CustodyBootstrapAnomaly as exc:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "code": exc.code,
                            "detail": exc.detail,
                            "samples": exc.samples,
                        },
                        default=str,
                        indent=2,
                    ),
                    file=sys.stderr,
                )
                await session.rollback()
                return 2

            if not args.dry_run:
                await session.commit()
            else:
                await session.rollback()

        print(json.dumps({"ok": True, **summary}, indent=2, default=str))
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(_amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
