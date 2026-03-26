"""READY short-circuit path: idempotent auth row repair."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.platform import PlatformTenant
from app.services import tenant_provisioning


@pytest.mark.asyncio
async def test_ready_repair_skips_when_db_name_missing():
    tenant = MagicMock(spec=PlatformTenant)
    tenant.db_name = None
    await tenant_provisioning._repair_tenant_auth_after_ready_if_needed(tenant, 1)


@pytest.mark.asyncio
async def test_ready_repair_wraps_sync_failure_as_http_500():
    tenant = MagicMock(spec=PlatformTenant)
    tenant.db_name = "tenant_x"

    with patch(
        "app.services.tenant_auth_sync_core.sync_tenant_auth_from_platform_members",
        new_callable=AsyncMock,
        side_effect=ValueError("simulated_sync_failure"),
    ):
        with pytest.raises(HTTPException) as ei:
            await tenant_provisioning._repair_tenant_auth_after_ready_if_needed(tenant, 3)
    assert ei.value.status_code == 500
    assert "reconciled" in ei.value.detail.lower() or "sync_tenant_auth" in ei.value.detail.lower()


def test_reconcile_before_rollback_script_importable():
    from app.scripts import reconcile_tenant_auth_before_rollback as mod

    assert hasattr(mod, "run")
