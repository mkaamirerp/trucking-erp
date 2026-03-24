#!/usr/bin/env python3
"""
Run tenant Alembic migrations for an existing tenant (creates loads/drivers tables if missing).

Usage (from project root, with DATABASE_URL or POSTGRES_ADMIN_URL set):
  PYTHONPATH=. python scripts/run_tenant_migrations.py <tenant_slug>
  e.g. PYTHONPATH=. python scripts/run_tenant_migrations.py acme

Requires: platform DB (DATABASE_URL) and tenant credentials (from POSTGRES_ADMIN_URL or
tenant_db_app_user / tenant_db_app_password). Runs: alembic -c alembic_tenant.ini upgrade head
with ALEMBIC_TENANT_DATABASE_URL pointing at the tenant's DB.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.platform import PlatformTenant
from app.services.tenant_provisioning import (
    _build_tenant_db_url,
    _run_tenant_migrations,
    _sanitize_db_name,
)


async def _get_tenant_db_url(slug: str) -> str:
    raw_admin = settings.postgres_admin_url or settings.database_url
    admin_url = to_async_pg_url(raw_admin)
    if not admin_url:
        raise SystemExit("POSTGRES_ADMIN_URL or DATABASE_URL required")

    from urllib.parse import urlparse
    parsed = urlparse(admin_url)
    app_user = settings.tenant_db_app_user or parsed.username
    app_pass = settings.tenant_db_app_password or parsed.password
    if not app_user or not app_pass:
        raise SystemExit("Tenant DB credentials required (POSTGRES_ADMIN_URL or tenant_db_app_*)")

    async with AsyncSessionLocal() as db:
        row = await db.execute(
            select(PlatformTenant).where(PlatformTenant.slug == slug).limit(1)
        )
        tenant = row.scalar_one_or_none()
    if not tenant:
        raise SystemExit(f"Tenant not found: {slug}")

    db_name = tenant.db_name
    if not db_name:
        safe = _sanitize_db_name(tenant.slug)
        if not safe:
            raise SystemExit(f"Invalid slug for DB name: {slug}")
        db_name = f"tenant_{safe}"

    return to_async_pg_url(_build_tenant_db_url(admin_url, db_name, app_user, app_pass))


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: PYTHONPATH=. python scripts/run_tenant_migrations.py <tenant_slug>", file=sys.stderr)
        sys.exit(2)
    slug = sys.argv[1].strip()
    if not slug:
        print("tenant_slug is required", file=sys.stderr)
        sys.exit(2)

    tenant_url = asyncio.run(_get_tenant_db_url(slug))
    os.chdir(PROJECT_ROOT)
    asyncio.run(_run_tenant_migrations(tenant_url, "head"))
    print(f"Tenant '{slug}' migrations upgraded to head.")


if __name__ == "__main__":
    main()
