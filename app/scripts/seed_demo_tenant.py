"""
One-off: ensure the "demo" workspace exists so demo.truckerp.me resolves.
Creates platform_tenants row (slug=demo) and provisions tenant DB if missing.
Run from repo root with env loaded (e.g. in container):
  set -a && . /run/secrets/truckerp.env  # or . .env
  set +a && cd /app && python -m app.scripts.seed_demo_tenant
"""
from __future__ import annotations

import asyncio
import os
import sys

# Load .env if present (dev)
if os.path.isfile(".env"):
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k and k not in os.environ:
                    os.environ[k] = v

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformTenant, TenantDBStatus, TenantStatus
from app.services.tenant_provisioning import provision_tenant_db

DEMO_SLUG = "demo"
DEMO_NAME = "Demo"


async def main() -> int:
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(PlatformTenant).where(PlatformTenant.slug == DEMO_SLUG)
        )
        if existing:
            if existing.db_status == "READY" and existing.status == "ACTIVE":
                print(f"Demo workspace already exists (tenant_id={existing.id}, db_name={existing.db_name})")
                return 0
            # Exists but not ready: provision
            print(f"Demo tenant exists but not ready (db_status={existing.db_status}). Provisioning...")
            try:
                await provision_tenant_db(int(existing.id), db, activate=True)
                await db.commit()
                print("Demo workspace provisioned and active.")
                return 0
            except Exception as e:
                await db.rollback()
                print(f"Provisioning failed: {e}", file=sys.stderr)
                return 1

        # Create new demo tenant then provision (assign id from sequence or max+1)
        next_id = await db.scalar(
            text("SELECT COALESCE(max(id), 0) + 1 FROM platform_tenants")
        )
        tenant = PlatformTenant(
            id=next_id,
            name=DEMO_NAME,
            slug=DEMO_SLUG,
            status=TenantStatus.PROVISIONING.value,
            db_status=TenantDBStatus.NOT_PROVISIONED.value,
        )
        db.add(tenant)
        await db.flush()
        print(f"Created demo tenant (id={tenant.id}). Provisioning DB...")
        try:
            await provision_tenant_db(int(tenant.id), db, activate=True)
            await db.commit()
            print("Demo workspace created and ready. Use https://demo.truckerp.me")
            return 0
        except Exception as e:
            await db.rollback()
            print(f"Provisioning failed: {e}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
