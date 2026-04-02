"""
Idempotent platform → tenant auth sync for cutover (run before tenant_auth_mode=tenant).

Usage (inside API container with secrets):
  python -m app.scripts.sync_tenant_auth_from_platform --tenant-id=53

Copies each workspace member's PlatformUser into tenant_users + tenant_workspace_members
and ensures platform_tenant_user_map rows exist. Preserves password_hash and session_version.
"""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.platform import PlatformTenant
from app.services.tenant_auth_sync_core import sync_tenant_auth_from_platform_members
from app.services.tenant_provisioning import _build_tenant_db_url


async def sync_tenant(tenant_id: int) -> None:
    async with AsyncSessionLocal() as pdb:
        tenant = await pdb.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))
    if not tenant or not tenant.db_name:
        raise ValueError("tenant not found or db_name not set (not provisioned)")

    raw_admin_url = settings.postgres_admin_url or settings.database_url
    admin_url = to_async_pg_url(raw_admin_url)
    app_user = settings.tenant_db_app_user
    app_pass = settings.tenant_db_app_password
    if not app_user or not app_pass:
        parsed_admin = urlparse(admin_url)
        if parsed_admin.username and parsed_admin.password:
            app_user = app_user or parsed_admin.username
            app_pass = app_pass or parsed_admin.password
    if not app_user or not app_pass:
        raise ValueError("tenant DB app credentials missing")

    tenant_db_url = to_async_pg_url(_build_tenant_db_url(admin_url, tenant.db_name, app_user, app_pass))
    await sync_tenant_auth_from_platform_members(int(tenant_id), tenant_db_url)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(sync_tenant(args.tenant_id))
    print(f"sync_tenant_auth_from_platform ok tenant_id={args.tenant_id}")


if __name__ == "__main__":
    main()
