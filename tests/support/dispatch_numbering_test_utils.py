"""
Direct SQL helpers for one negative-path integration test (missing trip prefix).

Scope: backup/delete/restore a single `tenant_dispatch_numbering` row only. Does not call app services;
keeps asserts honest for HTTP 409. Do not route normal tests through here.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.db_url import to_async_pg_url


def _tenant_async_url() -> str:
    from tests.support.integration_isolation import (
        IntegrationIsolationError,
        assert_tenant_database_url_allowed,
        require_integration_tenant_database_url,
    )

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        pytest.skip("TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL required to mutate numbering row")
    # Present URL that points at demo/shared DB must fail loudly (never skip).
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="dispatch_numbering_test_utils"))
    except IntegrationIsolationError:
        assert_tenant_database_url_allowed(raw, context="dispatch_numbering_test_utils")
        raise



@asynccontextmanager
async def temporarily_remove_dispatch_numbering_row(tenant_id: int) -> AsyncIterator[None]:
    """
    DELETE tenant_dispatch_numbering for tenant_id, yield, then restore prior row if one existed.

    If no row existed, leaves the table without a row for that tenant after the context
    (same as initial unconfigured state).
    """
    url = _tenant_async_url()
    eng: AsyncEngine = create_async_engine(url)
    backup: dict[str, Any] | None = None
    try:
        async with eng.begin() as conn:
            r = await conn.execute(
                text(
                    "SELECT tenant_id, trip_number_prefix, prefix_locked_at, next_numeric "
                    "FROM tenant_dispatch_numbering WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            )
            row = r.mappings().first()
            if row:
                backup = dict(row)
                await conn.execute(
                    text("DELETE FROM tenant_dispatch_numbering WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                )
        yield
    finally:
        try:
            async with eng.begin() as conn:
                await conn.execute(
                    text("DELETE FROM tenant_dispatch_numbering WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                )
                if backup is not None:
                    await conn.execute(
                        text(
                            "INSERT INTO tenant_dispatch_numbering "
                            "(tenant_id, trip_number_prefix, prefix_locked_at, next_numeric) "
                            "VALUES (:tenant_id, :trip_number_prefix, :prefix_locked_at, :next_numeric)"
                        ),
                        {
                            "tenant_id": backup["tenant_id"],
                            "trip_number_prefix": backup["trip_number_prefix"],
                            "prefix_locked_at": backup["prefix_locked_at"],
                            "next_numeric": backup["next_numeric"],
                        },
                    )
        finally:
            await eng.dispose()
