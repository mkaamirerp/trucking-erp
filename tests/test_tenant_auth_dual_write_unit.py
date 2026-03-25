"""Narrow unit tests for dual-write failure surface (no database)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.tenant_auth_dual_write import (
    apply_password_and_session_version_platform_primary,
    apply_password_and_session_version_tenant_primary,
)


@pytest.mark.asyncio
async def test_apply_password_platform_primary_runtime_error_when_map_missing_in_tenant_mode():
    platform_user = MagicMock()
    platform_user.id = "user-1"
    platform_user.session_version = 1
    platform_user.password_hash = None

    platform_db = MagicMock()
    platform_db.commit = AsyncMock()
    platform_db.refresh = AsyncMock()
    platform_db.scalar = AsyncMock(return_value=None)

    tenant_db = MagicMock()

    with pytest.raises(RuntimeError, match="dual_write_missing_map"):
        await apply_password_and_session_version_platform_primary(
            platform_db=platform_db,
            tenant_db=tenant_db,
            tenant_id=7,
            platform_user=platform_user,
            tenant_auth_mode="tenant",
            new_password_plain="x" * 12,
            bump_session=True,
        )


@pytest.mark.asyncio
async def test_apply_password_tenant_primary_runtime_error_when_map_missing():
    tu = MagicMock()
    tu.id = 42
    tu.session_version = 1
    tu.password_hash = None

    platform_db = MagicMock()
    platform_db.scalar = AsyncMock(return_value=None)
    tenant_db = MagicMock()
    tenant_db.commit = AsyncMock()
    tenant_db.refresh = AsyncMock()

    with pytest.raises(RuntimeError, match="dual_write_missing_map"):
        await apply_password_and_session_version_tenant_primary(
            platform_db=platform_db,
            tenant_db=tenant_db,
            tenant_id=7,
            tenant_user=tu,
            new_password_plain="y" * 12,
            bump_session=True,
        )
