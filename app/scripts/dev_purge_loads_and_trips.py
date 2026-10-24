"""
Dev playground only: remove all loads, trips, and load/trip operational rows for one tenant.

Does NOT delete drivers, brokers, fuel, tolls, fleet assets, people, or load_lab tables.

Guards:
  - Database name must be tenant_demo (override with ALLOWED_TENANT_DB=tenant_demo).
  - Set CONFIRM_PURGE_LOADS_TRIPS=YES_I_UNDERSTAND to execute (default is dry-run).

Run inside API container:
  docker exec truckerp-api bash -c 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.dev_purge_loads_and_trips'

Dry-run (default):
  DRY_RUN=1 python -m app.scripts.dev_purge_loads_and_trips

Execute:
  CONFIRM_PURGE_LOADS_TRIPS=YES_I_UNDERSTAND DRY_RUN=0 python -m app.scripts.dev_purge_loads_and_trips
"""
from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import PlatformTenant
from sqlalchemy import select

ALLOWED_DB_DEFAULT = "tenant_demo"
CONFIRM_ENV = "CONFIRM_PURGE_LOADS_TRIPS"
CONFIRM_VALUE = "YES_I_UNDERSTAND"
DEFAULT_SLUG = "demo"

COUNT_QUERIES: list[tuple[str, str]] = [
    ("loads", "SELECT count(*)::bigint FROM loads WHERE tenant_id = :t"),
    ("trips", "SELECT count(*)::bigint FROM trips WHERE tenant_id = :t"),
    ("dispatch_trips", "SELECT count(*)::bigint FROM dispatch_trips WHERE tenant_id = :t"),
    ("trip_loads", "SELECT count(*)::bigint FROM trip_loads WHERE tenant_id = :t"),
    ("future_movement_plans", "SELECT count(*)::bigint FROM future_movement_plans WHERE tenant_id = :t"),
    (
        "future_movement_plan_loads",
        "SELECT count(*)::bigint FROM future_movement_plan_loads WHERE tenant_id = :t",
    ),
    (
        "load_dispatch_instructions",
        "SELECT count(*)::bigint FROM load_dispatch_instructions WHERE tenant_id = :t",
    ),
    ("load_custody_events", "SELECT count(*)::bigint FROM load_custody_events WHERE tenant_id = :t"),
    ("load_pod_evidence", "SELECT count(*)::bigint FROM load_pod_evidence WHERE tenant_id = :t"),
    (
        "load_commercial_evidence",
        "SELECT count(*)::bigint FROM load_commercial_evidence WHERE tenant_id = :t",
    ),
    (
        "load_customs_snapshots",
        "SELECT count(*)::bigint FROM load_customs_snapshots WHERE tenant_id = :t",
    ),
    ("load_notes", "SELECT count(*)::bigint FROM load_notes WHERE tenant_id = :t"),
    ("load_stops", "SELECT count(*)::bigint FROM load_stops WHERE tenant_id = :t"),
    (
        "load_workspace_drafts",
        "SELECT count(*)::bigint FROM load_workspace_drafts WHERE tenant_id = :t",
    ),
    (
        "audit_events (load|trip)",
        "SELECT count(*)::bigint FROM audit_events WHERE tenant_id = :t AND entity_type IN ('load', 'trip')",
    ),
]


async def _platform_tenant_id_for_slug(slug: str) -> int:
    async with AsyncSessionLocal() as pdb:
        tid = await pdb.scalar(select(PlatformTenant.id).where(PlatformTenant.slug == slug.lower()))
    if tid is None:
        raise SystemExit(f"Platform tenant slug={slug!r} not found")
    return int(tid)


def _tenant_db_name() -> str:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL") or ""
    if not raw:
        raise SystemExit("TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL must be set")
    normalized = raw.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
    path = urlparse(normalized).path.lstrip("/")
    if not path:
        raise SystemExit("Could not parse tenant database name from URL")
    return path.split("?")[0]


def _assert_allowed_db() -> str:
    allowed = os.environ.get("ALLOWED_TENANT_DB", ALLOWED_DB_DEFAULT)
    db_name = _tenant_db_name()
    if db_name != allowed:
        raise SystemExit(
            f"Refusing purge: connected tenant DB is {db_name!r}, allowed is {allowed!r}. "
            f"Set ALLOWED_TENANT_DB only if you are certain."
        )
    return db_name


async def _counts(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, sql in COUNT_QUERIES:
        n = await db.scalar(text(sql), {"t": tenant_id})
        out[label] = int(n or 0)
    return out


async def execute_dev_playground_load_trip_reset(db: AsyncSession, tenant_id: int) -> None:
    """Delete all load/trip operational rows for tenant and reset trip number counter (prefix unchanged)."""
    await _purge(db, tenant_id)


async def _purge(db: AsyncSession, tenant_id: int) -> None:
    from app.constants.trip_dispatch import DEFAULT_NEXT_TRIP_NUMERIC

    t = tenant_id
    stmts: list[str] = [
        "DELETE FROM future_movement_plan_loads WHERE tenant_id = :t",
        "DELETE FROM future_movement_plans WHERE tenant_id = :t",
        "DELETE FROM load_dispatch_instructions WHERE tenant_id = :t",
        "DELETE FROM load_custody_events WHERE tenant_id = :t",
        "DELETE FROM trip_loads WHERE tenant_id = :t",
        "DELETE FROM load_stop_actions WHERE tenant_id = :t",
        "DELETE FROM load_pod_evidence WHERE tenant_id = :t",
        "DELETE FROM load_commercial_evidence WHERE tenant_id = :t",
        "DELETE FROM load_customs_snapshots WHERE tenant_id = :t",
        "DELETE FROM load_notes WHERE tenant_id = :t",
        "DELETE FROM load_stops WHERE tenant_id = :t",
        """UPDATE loads SET
            is_duplicate_of_load_id = NULL,
            promotion_origin_workspace_draft_id = NULL,
            active_trip_id = NULL,
            active_dispatch_trip_id = NULL,
            custody_trip_id = NULL,
            trip_number = NULL,
            driver_id = NULL,
            truck_id = NULL,
            trailer_id = NULL,
            custody_trailer_id = NULL
        WHERE tenant_id = :t""",
        "DELETE FROM trips WHERE tenant_id = :t",
        "DELETE FROM dispatch_trips WHERE tenant_id = :t",
        "UPDATE email_threads SET linked_load_id = NULL WHERE tenant_id = :t AND linked_load_id IS NOT NULL",
        (
            "UPDATE email_intake_qr_extractions SET linked_load_id = NULL "
            "WHERE tenant_id = :t AND linked_load_id IS NOT NULL"
        ),
        # Drafts before loads: promoted_load_id FK on load_workspace_drafts → loads.
        "DELETE FROM load_workspace_drafts WHERE tenant_id = :t",
        (
            "DELETE FROM audit_events WHERE tenant_id = :t AND entity_type IN ('load', 'trip')"
        ),
        "DELETE FROM loads WHERE tenant_id = :t",
        "UPDATE tenant_dispatch_numbering SET next_numeric = :next_n WHERE tenant_id = :t",
    ]
    for sql in stmts:
        if "next_numeric" in sql:
            await db.execute(text(sql), {"t": t, "next_n": DEFAULT_NEXT_TRIP_NUMERIC})
        else:
            await db.execute(text(sql), {"t": t})
    await db.commit()


async def main() -> int:
    db_name = _assert_allowed_db()
    slug = os.environ.get("PURGE_TENANT_SLUG", DEFAULT_SLUG)
    tenant_id = await _platform_tenant_id_for_slug(slug)
    dry_run = os.environ.get("DRY_RUN", "1").strip() not in ("0", "false", "no")
    confirmed = os.environ.get(CONFIRM_ENV, "").strip() == CONFIRM_VALUE

    print(f"Tenant DB: {db_name}")
    print(f"Platform slug: {slug} (tenant_id={tenant_id})")
    print(f"Mode: {'DRY_RUN (counts only)' if dry_run else 'EXECUTE PURGE'}")

    async for db in open_tenant_session_by_id(tenant_id):
        before = await _counts(db, tenant_id)
        print("\nCounts before:")
        for k, v in before.items():
            print(f"  {k}: {v}")

        if dry_run:
            print(
                f"\nDry-run only. To purge, run with DRY_RUN=0 and {CONFIRM_ENV}={CONFIRM_VALUE}"
            )
            return 0

        if not confirmed:
            raise SystemExit(
                f"Refusing purge without {CONFIRM_ENV}={CONFIRM_VALUE} (and DRY_RUN=0)"
            )

        await execute_dev_playground_load_trip_reset(db, tenant_id)
        after = await _counts(db, tenant_id)
        print("\nCounts after:")
        for k, v in after.items():
            print(f"  {k}: {v}")
        break

    print("\nPurge complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
