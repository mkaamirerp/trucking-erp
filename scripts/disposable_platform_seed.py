#!/usr/bin/env python3
"""Seed disposable platform DB: active pytest tenant, users, membership, Casbin pilot policy load."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from urllib.parse import urlparse

_REPO_ROOT = __file__.rsplit("/scripts/", 1)[0]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sqlalchemy import text

from app.core.verification_host_guard import (  # noqa: E402
    VerificationHostDenied,
    assert_disposable_verification_host,
    assert_verification_database_url,
)
from app.core.verification_subprocess_env import build_verification_subprocess_env  # noqa: E402

DEFAULT_SLUG = "pytest"
CERT_ADMIN_EMAIL = "verification-admin@example.test"


def _tenant_db_name() -> str:
    raw = (os.environ.get("TENANT_DATABASE_URL") or "").strip()
    if not raw:
        raise RuntimeError("TENANT_DATABASE_URL is required")
    return (urlparse(raw).path or "").lstrip("/").split("?", 1)[0]


def _db_host_port_user() -> tuple[str, int, str]:
    raw = (os.environ.get("TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL") or os.environ.get("DATABASE_URL") or "").strip()
    parsed = urlparse(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    user = parsed.username or "verify"
    return host, port, user


async def seed_disposable_platform() -> dict[str, str | int]:
    from app.authz.loader import load_prospective_policy
    from app.core.database import AsyncSessionLocal
    from app.models.platform import PlatformTenant, PlatformTenantMember, PlatformUser, TenantMembership

    slug = (os.environ.get("TRUCKERP_VERIFICATION_TENANT_SLUG") or DEFAULT_SLUG).strip().lower()
    tenant_db = _tenant_db_name()
    host, port, db_user = _db_host_port_user()

    async with AsyncSessionLocal() as db:
        current = await db.scalar(text("SELECT current_database()"))
        if not current or current.startswith("tenant_"):
            raise RuntimeError(f"refusing to seed tenant database {current}")

        await db.execute(text("DELETE FROM platform_subscriptions WHERE tenant_id IN (SELECT id FROM platform_tenants WHERE slug = :s)"), {"s": slug})
        await db.execute(text("DELETE FROM platform_tenant_members WHERE tenant_id IN (SELECT id FROM platform_tenants WHERE slug = :s)"), {"s": slug})
        await db.execute(text("DELETE FROM tenant_memberships WHERE tenant_id IN (SELECT id FROM platform_tenants WHERE slug = :s)"), {"s": slug})
        await db.execute(text("DELETE FROM platform_tenants WHERE slug = :s"), {"s": slug})
        await db.execute(
            text("DELETE FROM platform_users WHERE email = :e"),
            {"e": CERT_ADMIN_EMAIL},
        )
        await db.commit()

        admin = PlatformUser(
            id=str(uuid.uuid4()),
            email=CERT_ADMIN_EMAIL,
            first_name="Verification",
            last_name="Admin",
            status="ACTIVE",
            session_version=1,
        )
        tenant = PlatformTenant(
            name="Verification Pytest",
            slug=slug,
            status="ACTIVE",
            db_name=tenant_db,
            db_status="READY",
            db_host=host,
            db_port=port,
            db_user=db_user,
            tenant_auth_mode="platform",
        )
        db.add(admin)
        db.add(tenant)
        await db.flush()
        db.add(
            PlatformTenantMember(
                tenant_id=tenant.id,
                platform_user_id=admin.id,
                role="TENANT_ADMIN",
            )
        )
        db.add(
            TenantMembership(
                user_id=admin.id,
                tenant_id=tenant.id,
                status="active",
            )
        )
        await db.commit()
        tenant_id = int(tenant.id)
        admin_id = admin.id

    os.environ["CASBIN_LOAD_PILOT_ENFORCEMENT"] = "true"
    load_prospective_policy()
    return {
        "platform_tenant_slug": slug,
        "platform_tenant_id": tenant_id,
        "platform_admin_user_id": admin_id,
        "platform_admin_email": CERT_ADMIN_EMAIL,
        "tenant_database": tenant_db,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    try:
        assert_disposable_verification_host()
    except VerificationHostDenied as exc:
        print(f"VERIFICATION_SEED_DENIED: {exc}", file=sys.stderr)
        return 78

    platform_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not platform_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    assert_verification_database_url(platform_url, context="platform seed")

    # Ensure child imports see sanitized settings only.
    os.environ.update(
        build_verification_subprocess_env(
            {
                "DATABASE_URL": platform_url,
                "TENANT_DATABASE_URL": os.environ.get("TENANT_DATABASE_URL", ""),
                "CASBIN_LOAD_PILOT_ENFORCEMENT": "true",
            }
        )
    )

    try:
        result = asyncio.run(seed_disposable_platform())
    except Exception as exc:
        print(f"VERIFICATION_SEED_FAILED: {exc}", file=sys.stderr)
        return 1

    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
