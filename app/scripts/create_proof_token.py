"""
Create a one-off invite token for driver onboarding E2E proof.
Run inside the API container with env from /run/secrets/truckerp.env.

Usage:
  set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.create_proof_token [slug]

Output (to stdout): PROOF_TOKEN=<value>
Exit: 0 on success, 1 on error.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.application_access_token import ApplicationAccessToken
from app.models.person_application import PersonApplication
from app.models.platform import PlatformTenant


def _swap_db(url: str, db_name: str) -> str:
    base, _sep, _old = url.rpartition("/")
    return f"{base}/{db_name}" if base else url


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create proof invite token for driver onboarding E2E")
    parser.add_argument("slug", nargs="?", default="demo", help="Tenant slug (default: demo)")
    args = parser.parse_args()
    slug = (args.slug or "demo").strip().lower()
    if not slug:
        print("PROOF_TOKEN= slug is required", file=sys.stderr)
        return 1

    # Resolve tenant from platform DB
    async with AsyncSessionLocal() as platform_db:
        tenant = await platform_db.scalar(
            select(PlatformTenant).where(PlatformTenant.slug == slug).limit(1)
        )
    if not tenant:
        print(f"PROOF_TOKEN= tenant slug '{slug}' not found", file=sys.stderr)
        return 1
    if not tenant.db_name:
        print(f"PROOF_TOKEN= tenant '{slug}' has no db_name", file=sys.stderr)
        return 1

    template = getattr(settings, "postgres_admin_url", None) or settings.database_url
    if not template:
        print("PROOF_TOKEN= no database_url/postgres_admin_url", file=sys.stderr)
        return 1
    tenant_url = _swap_db(to_async_pg_url(template), tenant.db_name)

    engine = create_async_engine(tenant_url, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    token = "proof-e2e-" + os.urandom(16).hex()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=60)

    async with SessionLocal() as db:
        app = PersonApplication(
            tenant_id=tenant.id,
            status="DRAFT",
            source="invite_link",
            intake_payload={"step": "dl_upload"},
        )
        db.add(app)
        await db.flush()

        access = ApplicationAccessToken(
            tenant_id=tenant.id,
            application_id=app.id,
            token=token,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked_at=None,
            purpose="invite",
        )
        db.add(access)
        await db.commit()

    print(f"PROOF_TOKEN={token}")
    print(f"PROOF_SLUG={slug}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
