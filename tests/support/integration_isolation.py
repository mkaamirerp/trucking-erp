"""Integration-test isolation: dedicated pytest tenant only (never demo / tenant_demo).

Import AUTH_HEADERS / require_* helpers from here instead of hardcoding pytest.truckerp.me.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.integration_db_guard import (
    DEFAULT_INTEGRATION_TENANT_DB_NAME,
    DEFAULT_INTEGRATION_TENANT_SLUG,
    FORBIDDEN_INTEGRATION_TENANT_DB_NAMES,
    FORBIDDEN_INTEGRATION_TENANT_SLUGS,
    IntegrationIsolationError,
    allowed_integration_db_names,
    allowed_integration_slugs,
    assert_environment_allows_integration_mutation,
    assert_integration_db_name_allowed,
    assert_integration_host_allowed,
    assert_integration_tenant_slug_allowed,
    assert_tenant_database_url_allowed,
    database_name_from_url,
    integration_tenant_db_name,
    integration_tenant_slug,
)

__all__ = [
    "AUTH_HEADERS",
    "DEFAULT_INTEGRATION_TENANT_DB_NAME",
    "DEFAULT_INTEGRATION_TENANT_SLUG",
    "FORBIDDEN_INTEGRATION_TENANT_DB_NAMES",
    "FORBIDDEN_INTEGRATION_TENANT_SLUGS",
    "INTEGRATION_AUTH_HOST",
    "IntegrationIsolationError",
    "allowed_integration_db_names",
    "allowed_integration_slugs",
    "assert_environment_allows_integration_mutation",
    "assert_integration_db_name_allowed",
    "assert_integration_host_allowed",
    "assert_integration_tenant_identity_allowed",
    "assert_integration_tenant_slug_allowed",
    "assert_mutating_integration_allowed",
    "assert_tenant_database_url_allowed",
    "database_name_from_url",
    "integration_auth_headers",
    "integration_tenant_db_name",
    "integration_tenant_slug",
    "require_integration_tenant_database_url",
]


def integration_auth_host() -> str:
    return f"{integration_tenant_slug()}.truckerp.me"


def integration_auth_headers() -> dict[str, str]:
    host = integration_auth_host()
    assert_integration_host_allowed(host, context="integration_auth_headers")
    return {"host": host}


# Eager headers for modules that assign AUTH_HEADERS = ... at import time.
# Host is re-validated on mutating helper / TEST_BYPASS paths.
AUTH_HEADERS = {"host": f"{DEFAULT_INTEGRATION_TENANT_SLUG}.truckerp.me"}
INTEGRATION_AUTH_HOST = f"{DEFAULT_INTEGRATION_TENANT_SLUG}.truckerp.me"

def require_integration_tenant_database_url(*, context: str = "tenant_database_url") -> str:
    """Return TENANT_DATABASE_URL / ALEMBIC_TENANT_DATABASE_URL after hard isolation checks."""
    assert_environment_allows_integration_mutation(context=context)
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    assert_tenant_database_url_allowed(raw, context=context)
    return str(raw).strip()


def assert_integration_tenant_identity_allowed(
    *,
    slug: str | None = None,
    db_name: str | None = None,
    tenant_id: int | None = None,
    context: str = "tenant_identity",
) -> None:
    assert_environment_allows_integration_mutation(context=context)
    if slug is not None:
        assert_integration_tenant_slug_allowed(slug, context=context)
    if db_name is not None:
        assert_integration_db_name_allowed(db_name, context=context)
    if tenant_id is not None:
        # Resolve via platform when available; sync denylist of known demo id is insufficient alone.
        # Callers that only have tenant_id should use assert_mutating_integration_allowed.
        pass


async def assert_mutating_integration_allowed(
    *,
    tenant_id: int | None = None,
    host: str | None = None,
    context: str = "mutating_integration",
) -> None:
    """Hard gate before ORM/HTTP mutations. Fails on demo / non-dedicated tenant."""
    assert_environment_allows_integration_mutation(context=context)

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if raw:
        assert_tenant_database_url_allowed(raw, context=context)

    if host is not None:
        assert_integration_host_allowed(host, context=context)

    if tenant_id is None:
        return

    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.platform import PlatformTenant

    async with AsyncSessionLocal() as session:
        row = await session.scalar(select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)))
    if row is None:
        raise IntegrationIsolationError(
            f"Integration isolation: tenant_id={tenant_id} not found in platform registry ({context})."
        )
    assert_integration_tenant_slug_allowed(row.slug, context=f"{context}:tenant_id={tenant_id}")
    assert_integration_db_name_allowed(row.db_name, context=f"{context}:tenant_id={tenant_id}")


def pytest_enforce_tenant_database_env() -> None:
    """Call from pytest_sessionstart when tenant URL env is present."""
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return
    assert_tenant_database_url_allowed(raw, context="pytest_sessionstart")
