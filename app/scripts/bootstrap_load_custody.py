#!/usr/bin/env python3
"""One-time custody bootstrap after migration d7e8f0a1b2c3.

Usage (inside truckerp-api with secrets):

  set -a && . /run/secrets/truckerp.env && set +a
  cd /app
  python -m app.scripts.bootstrap_load_custody --tenant-id 1
  python -m app.scripts.bootstrap_load_custody --tenant-id 1 --dry-run
  python -m app.scripts.bootstrap_load_custody --all-tenants-with-active

Does NOT invent yard/history. Stops on ACTIVE membership anomalies.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.services.load_custody import (
    CustodyBootstrapAnomaly,
    bootstrap_load_custody_for_tenant,
    preflight_custody_bootstrap_anomalies,
)


def _tenant_url() -> str:
    import os

    raw = os.environ.get("ALEMBIC_TENANT_DATABASE_URL") or os.environ.get("TENANT_DATABASE_URL")
    if not raw:
        raise SystemExit("ALEMBIC_TENANT_DATABASE_URL or TENANT_DATABASE_URL required")
    return to_async_pg_url(raw)


async def _tenant_ids(session: AsyncSession, all_with_active: bool, tenant_id: int | None) -> list[int]:
    if tenant_id is not None:
        return [tenant_id]
    if all_with_active:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT tenant_id
                    FROM trip_loads
                    WHERE status_within_trip = 'active'
                      AND completed_at IS NULL
                      AND removed_at IS NULL
                    ORDER BY tenant_id
                    """
                )
            )
        ).scalars().all()
        return [int(x) for x in rows]
    raise SystemExit("Pass --tenant-id N or --all-tenants-with-active")


async def _amain(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Bootstrap Load custody snapshots from ACTIVE TripLoads")
    p.add_argument("--tenant-id", type=int, default=None)
    p.add_argument("--all-tenants-with-active", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    args = p.parse_args(argv)

    engine = create_async_engine(_tenant_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    results: list[dict] = []
    try:
        async with Session() as session:
            # Global anomaly scan when all-tenants
            scan_tid = None if args.all_tenants_with_active else args.tenant_id
            try:
                await preflight_custody_bootstrap_anomalies(session, tenant_id=scan_tid)
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
                    ),
                    file=sys.stderr,
                )
                return 2

            if args.preflight_only:
                print(json.dumps({"ok": True, "preflight": "passed"}))
                return 0

            tids = await _tenant_ids(session, args.all_tenants_with_active, args.tenant_id)
            for tid in tids:
                try:
                    summary = await bootstrap_load_custody_for_tenant(
                        session, tid, dry_run=args.dry_run
                    )
                    results.append(summary)
                except CustodyBootstrapAnomaly as exc:
                    print(
                        json.dumps(
                            {
                                "ok": False,
                                "tenant_id": tid,
                                "code": exc.code,
                                "detail": exc.detail,
                                "samples": exc.samples,
                            },
                            default=str,
                        ),
                        file=sys.stderr,
                    )
                    await session.rollback()
                    return 2

            if not args.dry_run:
                await session.commit()
            else:
                await session.rollback()

        print(json.dumps({"ok": True, "results": results}, indent=2))
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(_amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
