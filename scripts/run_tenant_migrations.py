#!/usr/bin/env python3
"""
Legacy host-side helper: resolves a tenant slug to a DB URL and runs one tenant Alembic target.

**Not the canonical operator path.** Routine production tenant upgrades must use
``scripts/tenant_upgrade_revision.sh`` in ``truckerp-api`` (preflight + env gate).
See ``docs/load_trip/POD_MIGRATION_TARGETS.md``.

While ``i14_load_pod_evidence`` and ``i14_load_pod_evidence_x5`` are both heads, ``head`` is
refused. Pass one of those revisions explicitly. A single future head restores ``head``.

Usage (from project root, with DATABASE_URL or POSTGRES_ADMIN_URL set):
  PYTHONPATH=. python scripts/run_tenant_migrations.py <tenant_slug> <revision>
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

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.platform import PlatformTenant
from app.services.tenant_provisioning import (
    _build_tenant_db_url,
    _run_tenant_migrations,
    _sanitize_db_name,
)
from scripts.tenant_revision_plan import RevisionPlanError, migration_target_for_request


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


async def _current_revision(tenant_url: str) -> str | None:
    engine = create_async_engine(tenant_url)
    try:
        async with engine.connect() as conn:
            rows = list((await conn.execute(text("select version_num from alembic_version"))).scalars().all())
    finally:
        await engine.dispose()
    if len(rows) > 1:
        raise SystemExit(f"multiple alembic_version rows; refusing upgrade: {rows}")
    return rows[0] if rows else None


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(PROJECT_ROOT / "alembic_tenant.ini")))


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print(
            "Usage: PYTHONPATH=. python scripts/run_tenant_migrations.py <tenant_slug> [revision]\n\n"
            "While the I14 POD heads are split, revision is required and must be\n"
            "i14_load_pod_evidence_x5 or i14_load_pod_evidence. head is refused.\n",
            file=sys.stderr,
        )
        sys.exit(2)
    slug = sys.argv[1].strip()
    requested = sys.argv[2].strip() if len(sys.argv) == 3 else None
    if not slug:
        print("tenant_slug is required", file=sys.stderr)
        sys.exit(2)

    _print_legacy_stderr_notice()
    if requested in (None, "", "head", "heads"):
        try:
            migration_target_for_request(_script(), None, requested)
        except RevisionPlanError as exc:
            print(f"Refusing upgrade: {exc}", file=sys.stderr)
            sys.exit(1)

    tenant_url = asyncio.run(_get_tenant_db_url(slug))
    current = asyncio.run(_current_revision(tenant_url))
    try:
        target = migration_target_for_request(_script(), current, requested)
    except RevisionPlanError as exc:
        print(f"Refusing upgrade: {exc}", file=sys.stderr)
        sys.exit(1)
    if current == target:
        print(f"Tenant '{slug}' already at {target}; no migration run.")
        return
    os.chdir(PROJECT_ROOT)
    asyncio.run(_run_tenant_migrations(tenant_url, target))
    print(f"Tenant '{slug}' migrations upgraded to {target}.")


if __name__ == "__main__":
    main()
