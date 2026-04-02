"""
Pre-cutover checks: compare platform member count to tenant auth rows and map coverage.

Usage:
  python -m app.scripts.verify_tenant_auth_cutover --tenant-id=53
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformTenantMember
from app.services.tenant_auth_cutover_verify import collect_tenant_auth_cutover_errors


async def verify(tenant_id: int) -> int:
    errors = await collect_tenant_auth_cutover_errors(tenant_id)
    if errors:
        print("VERIFY FAILED:")
        for e in errors:
            print(" -", e)
        return 1
    async with AsyncSessionLocal() as pdb:
        n_ptm = int(
            (
                await pdb.scalar(
                    select(func.count()).select_from(PlatformTenantMember).where(
                        PlatformTenantMember.tenant_id == int(tenant_id)
                    )
                )
            )
            or 0
        )
    print(f"verify_tenant_auth_cutover OK tenant_id={tenant_id} members={n_ptm}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", type=int, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify(args.tenant_id)))


if __name__ == "__main__":
    main()
