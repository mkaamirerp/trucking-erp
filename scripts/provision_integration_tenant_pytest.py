"""One-shot provision of dedicated integration tenant (slug=pytest, db=tenant_pytest)."""
from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url, to_sync_pg_url
from app.core.config import settings


def _redact(url: str) -> str:
    p = urlparse(url)
    netloc = p.hostname or ""
    if p.port:
        netloc = f"{netloc}:{p.port}"
    if p.username:
        netloc = f"{p.username}:***@{netloc}"
    return urlunparse((p.scheme, netloc, p.path, "", "", ""))


def _swap_db(url: str, db_name: str) -> str:
    base, _, _old = url.rpartition("/")
    return f"{base}/{db_name}"


async def main() -> None:
    slug = os.environ.get("TRUCKERP_INTEGRATION_TENANT_SLUG", "pytest")
    db_name = os.environ.get("TRUCKERP_INTEGRATION_TENANT_DB", "tenant_pytest")
    admin = getattr(settings, "postgres_admin_url", None) or settings.database_url
    if not admin:
        raise SystemExit("DATABASE_URL / postgres_admin_url missing")

    print("admin", _redact(admin))
    print("target", db_name, "slug", slug)

    # 1) CREATE DATABASE if needed (via async admin connection to postgres)
    admin_async = to_async_pg_url(_swap_db(admin, "postgres"))
    eng = create_async_engine(admin_async, isolation_level="AUTOCOMMIT")
    try:
        async with eng.connect() as conn:
            exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name})
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print("created database", db_name)
            else:
                print("database already exists", db_name)
    finally:
        await eng.dispose()

    # 2) Schema: clone from tenant_demo if target has no loads table
    target_async = to_async_pg_url(_swap_db(admin, db_name))
    teng = create_async_engine(target_async)
    try:
        async with teng.connect() as conn:
            has_loads = await conn.scalar(
                text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='loads'")
            )
    finally:
        await teng.dispose()

    if not has_loads:
        src = to_sync_pg_url(_swap_db(admin, "tenant_demo"))
        dst = to_sync_pg_url(_swap_db(admin, db_name))
        print("cloning schema from tenant_demo ->", db_name, "(no data)")
        # schema-only dump restore
        dump = subprocess.run(
            ["pg_dump", "--schema-only", "--no-owner", "--no-acl", src],
            check=True,
            capture_output=True,
        )
        # filter platform-ish? tenant_demo is tenant schema only
        subprocess.run(["psql", dst, "-v", "ON_ERROR_STOP=1"], input=dump.stdout, check=True)
        print("schema clone done")
    else:
        print("schema already present")

    # 3) Platform tenant + subscription
    async with AsyncSessionLocal() as db:
        row = (await db.execute(text("SELECT id, slug, db_name, status, db_status FROM platform_tenants WHERE slug=:s"), {"s": slug})).mappings().first()
        demo = (await db.execute(text("SELECT db_host, db_port, db_user FROM platform_tenants WHERE slug='demo'"))).mappings().one()
        if row:
            tid = int(row["id"])
            await db.execute(
                text(
                    "UPDATE platform_tenants SET db_name=:db, status='ACTIVE', db_status='READY', "
                    "db_host=:h, db_port=:p, db_user=:u, updated_at=now(), provisioned_at=COALESCE(provisioned_at, now()) "
                    "WHERE id=:id"
                ),
                {"db": db_name, "h": demo["db_host"], "p": demo["db_port"], "u": demo["db_user"], "id": tid},
            )
            print("updated platform tenant", tid)
        else:
            # Insert mirroring demo connection meta without copying credentials columns we don't have in SELECT
            r = await db.execute(
                text(
                    """
                    INSERT INTO platform_tenants
                      (name, slug, status, db_host, db_port, db_name, db_user, db_status, provisioned_at,
                       base_currency, timezone, country_code, privacy_mode, audit_visibility_mode,
                       email_provider_type, tenant_auth_mode, created_at, updated_at)
                    VALUES
                      ('pytest-integration', :slug, 'ACTIVE', :h, :p, :db, :u, 'READY', now(),
                       'USD', 'America/Toronto', 'CA', 'standard', 'tenant_support',
                       'platform_smtp', 'platform', now(), now())
                    RETURNING id
                    """
                ),
                {"slug": slug, "h": demo["db_host"], "p": demo["db_port"], "db": db_name, "u": demo["db_user"]},
            )
            tid = int(r.scalar_one())
            print("inserted platform tenant", tid)

        sub = await db.scalar(text("SELECT id FROM platform_subscriptions WHERE tenant_id=:t"), {"t": tid})
        if not sub:
            await db.execute(
                text(
                    "INSERT INTO platform_subscriptions (tenant_id, plan, status, trial_ends_at, created_at, updated_at) "
                    "VALUES (:t, 'TRIAL', 'TRIAL_ACTIVE', now() + interval '365 days', now(), now())"
                ),
                {"t": tid},
            )
            print("subscription created")
        await db.commit()

    # 4) Tenant numbering + minimal driver/truck if empty
    teng = create_async_engine(target_async)
    try:
        async with teng.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO tenant_dispatch_numbering (tenant_id, trip_number_prefix, prefix_locked_at, next_numeric)
                    VALUES (:t, 'PYT', now(), 10001)
                    ON CONFLICT (tenant_id) DO NOTHING
                    """
                ),
                {"t": tid},
            )
            # drivers/trucks minimal for trip tests — check tables
            dcount = await conn.scalar(text("SELECT count(*) FROM drivers"))
            tcount = await conn.scalar(text("SELECT count(*) FROM trucks"))
            print("drivers", dcount, "trucks", tcount)
            if int(dcount or 0) == 0:
                # inspect required columns
                cols = [r[0] for r in (await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='drivers' AND is_nullable='NO'"
                ))).fetchall()]
                print("drivers_not_null", cols)
    finally:
        await teng.dispose()

    print("DONE tenant_id", tid, "db", db_name, "slug", slug)


asyncio.run(main())
