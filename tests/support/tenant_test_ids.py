"""
Platform DB read: map slug → `platform_tenants.id`.

Use for aligning ORM fixtures with the same tenant the Host header uses for TEST_BYPASS.
Defaults to the dedicated integration slug (`pytest`), never `demo`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformTenant
from tests.support.integration_isolation import (
    assert_integration_db_name_allowed,
    assert_integration_tenant_slug_allowed,
    integration_tenant_slug,
)


async def platform_tenant_id_for_slug(slug: str | None = None) -> int:
    """ACTIVE integration-tenant resolution: same slug the Host header uses for TEST_BYPASS."""
    resolved = (slug or integration_tenant_slug()).strip().lower()
    assert_integration_tenant_slug_allowed(resolved, context="platform_tenant_id_for_slug")
    async with AsyncSessionLocal() as session:
        row = await session.scalar(select(PlatformTenant).where(PlatformTenant.slug == resolved))
    if row is None:
        pytest.skip(f"platform tenant slug={resolved!r} not found")
    assert_integration_db_name_allowed(row.db_name, context=f"platform_tenant_id_for_slug:{resolved}")
    return int(row.id)
