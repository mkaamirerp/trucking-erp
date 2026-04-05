#!/usr/bin/env python3
"""
Legacy host-side helper: resolves a tenant slug to a DB URL and runs tenant Alembic to ``head``.

**Not the canonical operator path.** Routine production tenant upgrades must use
``scripts/tenant_upgrade_head.sh`` in ``truckerp-api`` (preflight + env gate), e.g. via
``./scripts/db_run.sh`` — see ``docs/secrets.md`` and ``.cursor/rules/tenant-migrations.mdc``.

This script skips that wrapper (raw ``python -m alembic -c alembic_tenant.ini upgrade …`` via
``app.services.tenant_provisioning._run_tenant_migrations``). Prefer the wrapper for operators;
keep this entrypoint only for narrow legacy/host workflows until fully deprecated.

Usage (from project root, with DATABASE_URL or POSTGRES_ADMIN_URL set):
  PYTHONPATH=. python scripts/run_tenant_migrations.py <tenant_slug>
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


def _print_legacy_stderr_notice() -> None:
    print(
        "WARNING: run_tenant_migrations.py is legacy/host-side and skips tenant preflight "
        "(not the operator path). Use scripts/tenant_upgrade_head.sh — see docs/secrets.md.\n",
        file=sys.stderr,
    )


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: PYTHONPATH=. python scripts/run_tenant_migrations.py <tenant_slug>\n\n"
            "Non-canonical: operators should run bash scripts/tenant_upgrade_head.sh in truckerp-api "
            "(docs/secrets.md, db_run.sh).\n",
            file=sys.stderr,
        )
        sys.exit(2)
    slug = sys.argv[1].strip()
    if not slug:
        print("tenant_slug is required", file=sys.stderr)
        sys.exit(2)

    _print_legacy_stderr_notice()
    tenant_url = asyncio.run(_get_tenant_db_url(slug))
    os.chdir(PROJECT_ROOT)
    asyncio.run(_run_tenant_migrations(tenant_url, "head"))
    print(f"Tenant '{slug}' migrations upgraded to head.")


if __name__ == "__main__":
    main()
