"""
Platform DB read: map slug → `platform_tenants.id`.

Use for aligning ORM fixtures with the same tenant the Host header resolves. Not for creating tenants.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformTenant


async def platform_tenant_id_for_slug(slug: str) -> int:
    """ACTIVE demo-style resolution: same slug the Host header uses for TEST_BYPASS."""
    async with AsyncSessionLocal() as session:
        tid = await session.scalar(select(PlatformTenant.id).where(PlatformTenant.slug == slug.lower()))
    if tid is None:
        pytest.skip(f"platform tenant slug={slug!r} not found")
    return int(tid)
