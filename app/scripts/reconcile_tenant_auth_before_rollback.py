"""
Trust restore before rollback to platform auth:

1. python -m app.scripts.sync_tenant_auth_from_platform --tenant-id=<id>
2. python -m app.scripts.verify_tenant_auth_cutover --tenant-id=<id>

This script runs both; exits non-zero if verify reports drift or sync fails.

Usage (API container):
  python -m app.scripts.reconcile_tenant_auth_before_rollback --tenant-id=53
"""
from __future__ import annotations

import asyncio
import sys

import argparse
from urllib.parse import urlparse

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.platform import PlatformTenant
from app.services.tenant_auth_cutover_verify import collect_tenant_auth_cutover_errors
from app.services.tenant_auth_sync_core import sync_tenant_auth_from_platform_members
from app.services.tenant_provisioning import _build_tenant_db_url


def _tenant_db_url_for(tenant: PlatformTenant) -> str:
    raw_admin_url = settings.postgres_admin_url or settings.database_url
    admin_url = to_async_pg_url(raw_admin_url)
    app_user = settings.tenant_db_app_user
    app_pass = settings.tenant_db_app_password
    if not app_user or not app_pass:
        parsed_admin = urlparse(admin_url)
        if parsed_admin.username and parsed_admin.password:
            app_user = app_user or parsed_admin.username
            app_pass = app_pass or parsed_admin.password
    if not app_user or not app_pass or not tenant.db_name:
        raise SystemExit("Missing tenant DB URL/credentials or tenant.db_name")
    return to_async_pg_url(_build_tenant_db_url(admin_url, tenant.db_name, app_user, app_pass))


async def run(tenant_id: int) -> int:
    async with AsyncSessionLocal() as db:
        tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))
    if not tenant:
        print("reconcile: tenant not found", file=sys.stderr)
        return 2
    url = _tenant_db_url_for(tenant)
    print(f"reconcile: syncing tenant_id={tenant_id} ...")
    await sync_tenant_auth_from_platform_members(int(tenant_id), url)
    errors = await collect_tenant_auth_cutover_errors(int(tenant_id))
    if errors:
        print("reconcile: VERIFY FAILED after sync — fix drift before trusting rollback:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1
    print(f"reconcile: OK tenant_id={tenant_id} (sync + verify clean)")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", type=int, required=True)
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args.tenant_id)))


if __name__ == "__main__":
    main()
