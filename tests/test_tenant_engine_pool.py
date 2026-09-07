"""Tenant engines must not use the default 5+10 QueuePool."""

from __future__ import annotations

from app.deps.tenant_db import _TENANT_ENGINE_KWARGS


def test_tenant_engine_pool_is_capped() -> None:
    assert _TENANT_ENGINE_KWARGS["pool_size"] == 1
    assert _TENANT_ENGINE_KWARGS["max_overflow"] == 4
    assert _TENANT_ENGINE_KWARGS["pool_pre_ping"] is True
    # Default SQLAlchemy QueuePool is 5+10; that is what filled max_connections=100.
    assert _TENANT_ENGINE_KWARGS["pool_size"] + _TENANT_ENGINE_KWARGS["max_overflow"] <= 5
