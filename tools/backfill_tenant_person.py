#!/usr/bin/env python3
"""
Backfill a people row (and OWNER role) in a tenant DB for a platform user.

Use when login works but the tenant DB has no people row for that user (e.g. tenant
was provisioned before creator-seed existed, or via a flow that didn't pass creator).

Run from repo root with app env loaded (e.g. .env or /run/secrets/truckerp.env):

  python tools/backfill_tenant_person.py <tenant_slug> <platform_user_id>

Example:

  python tools/backfill_tenant_person.py demo 3e880f9c-24f6-4312-8877-0f6161a85328
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Run from repo root so app is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python tools/backfill_tenant_person.py <tenant_slug> <platform_user_id>", file=sys.stderr)
        sys.exit(2)
    tenant_slug = sys.argv[1].strip()
    platform_user_id = sys.argv[2].strip()
    from app.services.tenant_provisioning import backfill_tenant_creator_person

    ok = await backfill_tenant_creator_person(tenant_slug, platform_user_id)
    if ok:
        print("Backfill completed. The people row (and OWNER role) now exist or already existed.")
    else:
        print("Backfill failed: tenant or platform user not found, or DB credentials missing.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
