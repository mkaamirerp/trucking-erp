"""
Run scripts/tenant_upgrade_head.sh for every ACTIVE + READY tenant with db_name.

Must run inside truckerp-api at /app with platform DB env loaded:

  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.tenant_fleet_upgrade_head'

Uses the same tenant DB URL construction as open_tenant_session_by_id (postgres_admin_url or database_url + db_name).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.platform import PlatformTenant


def _swap_db(url: str, db_name: str) -> str:
    base, _sep, _old = url.rpartition("/")
    return f"{base}/{db_name}" if base else url


def _tenant_alembic_url(db_name: str) -> str:
    template = getattr(settings, "postgres_admin_url", None) or settings.database_url
    if not template:
        raise RuntimeError("database_url / postgres_admin_url not configured")
    return _swap_db(to_async_pg_url(template), db_name)


async def _tenant_targets() -> list[tuple[int, str]]:
    async with AsyncSessionLocal() as pdb:
        result = await pdb.execute(
            select(PlatformTenant.id, PlatformTenant.db_name).where(
                PlatformTenant.status == "ACTIVE",
                PlatformTenant.db_status == "READY",
                PlatformTenant.db_name.isnot(None),
            )
        )
        return [(int(r[0]), str(r[1])) for r in result.all()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tenant-id",
        type=int,
        default=None,
        help="Only upgrade this platform tenant id (for spot fixes).",
    )
    args = parser.parse_args()
    rc = asyncio.run(_run(filter_tid=args.tenant_id))
    raise SystemExit(rc)


async def _run(filter_tid: int | None) -> int:
    targets = await _tenant_targets()
    if filter_tid is not None:
        targets = [(tid, db) for tid, db in targets if tid == filter_tid]

    if not targets:
        print("tenant_fleet_upgrade_head: no matching tenants", file=sys.stderr)
        return 0

    ok = 0
    failed = 0
    for tid, db_name in sorted(targets, key=lambda x: x[0]):
        try:
            alembic_url = _tenant_alembic_url(db_name)
        except Exception as exc:
            print(f"tenant_id={tid} db_name={db_name} url build failed: {exc}", file=sys.stderr)
            failed += 1
            continue
        env = os.environ.copy()
        env["ALEMBIC_TENANT_DATABASE_URL"] = alembic_url
        print(f"tenant_id={tid} db_name={db_name} -> upgrade head ...", flush=True)
        proc = await asyncio.to_thread(
            subprocess.run,
            ["bash", "scripts/tenant_upgrade_head.sh"],
            cwd="/app",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            ok += 1
        else:
            failed += 1
            print(proc.stdout or "", file=sys.stderr)
            print(proc.stderr or "", file=sys.stderr)
            print(f"tenant_id={tid} upgrade FAILED exit={proc.returncode}", file=sys.stderr)

    print(f"tenant_fleet_upgrade_head: ok={ok} failed={failed} total={len(targets)}")
    return 1 if failed else 0


if __name__ == "__main__":
    main()
