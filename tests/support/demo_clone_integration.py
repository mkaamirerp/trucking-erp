"""Helpers for pytest against a disposable tenant_demo clone (demo_clone_runner only)."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import assert_integration_db_name_allowed, database_name_from_url
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant_db import get_tenant_db


def demo_clone_active() -> bool:
    raw = os.environ.get("TENANT_DATABASE_URL") or ""
    return (
        os.environ.get("DEMO_CLONE_EXTERNAL_EFFECTS") == "disabled"
        and "tenant_clone_" in raw
    )


def demo_clone_tenant_id() -> int:
    explicit = (os.environ.get("TRUCKERP_DEMO_CLONE_TENANT_ID") or "").strip()
    if explicit:
        return int(explicit)
    return 53


def demo_clone_database_name() -> str:
    raw = os.environ.get("TENANT_DATABASE_URL") or ""
    name = database_name_from_url(raw)
    assert_integration_db_name_allowed(name, context="demo_clone_integration")
    return name


def install_demo_clone_tenant_db_override(app: Any) -> None:
    if not demo_clone_active():
        return
    tenant_url = to_async_pg_url(os.environ["TENANT_DATABASE_URL"])

    async def _tenant_db(_request: Request) -> AsyncGenerator[AsyncSession, None]:
        engine = create_async_engine(tenant_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with session_factory() as session:
            yield session
        await engine.dispose()

    app.dependency_overrides[get_tenant_db] = _tenant_db
    # Clone tenant (e.g. id=53) has no platform_phase4c subscription row; tests still use TENANT_ADMIN role.
    if demo_clone_active():
        app.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None


def install_demo_clone_http_test_overrides(app: Any) -> None:
    """Tenant DB routing + admin_sensitive bypass for disposable clone HTTP tests."""
    install_demo_clone_tenant_db_override(app)


def clear_demo_clone_http_test_overrides(app: Any) -> None:
    app.dependency_overrides.pop(require_admin_sensitive_entitlement, None)
