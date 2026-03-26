"""
End-to-end: collect_tenant_auth_cutover_errors detects session_version drift and recovers after fix.

Requires DATABASE_URL, ACTIVE tenant with at least one PlatformTenantUserMap + TenantUser in sync.

Env:
  RUN_DRIFT_CUTOVER_E2E=1
  DRIFT_E2E_TENANT_ID=<platform_tenants.id>

Run (example):
  docker run --rm -e DATABASE_URL=... -e RUN_DRIFT_CUTOVER_E2E=1 -e DRIFT_E2E_TENANT_ID=53 \\
    -v "$(pwd):/app" -w /app --entrypoint python trucking_erp-truckerp-api \\
    -m pytest tests/test_tenant_auth_cutover_drift_e2e.py -v
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import PlatformTenantUserMap, PlatformUser
from app.models.tenant_auth import TenantUser
from app.services.tenant_auth_cutover_verify import collect_tenant_auth_cutover_errors

SKIP_NO_DB = not os.environ.get("DATABASE_URL")
RUN = os.environ.get("RUN_DRIFT_CUTOVER_E2E") == "1"
TID_RAW = os.environ.get("DRIFT_E2E_TENANT_ID")
SKIP = SKIP_NO_DB or not RUN or not TID_RAW


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP, reason="RUN_DRIFT_CUTOVER_E2E=1 and DRIFT_E2E_TENANT_ID required")
async def test_collect_cutover_errors_reports_session_version_drift_and_restores():
    tid = int(TID_RAW)
    base = await collect_tenant_auth_cutover_errors(tid)
    if base:
        pytest.skip("baseline must be clean: " + "; ".join(base))

    pmap = None
    pu = None
    async with AsyncSessionLocal() as pdb:
        pmap = await pdb.scalar(
            select(PlatformTenantUserMap).where(PlatformTenantUserMap.tenant_id == tid).limit(1)
        )
        if not pmap:
            pytest.skip("no platform_tenant_user_map row for tenant")
        pu = await pdb.get(PlatformUser, str(pmap.platform_user_id))
        if not pu:
            pytest.skip("mapped platform user missing")

    async for tdb in open_tenant_session_by_id(tid):
        tu = await tdb.scalar(
            select(TenantUser).where(
                TenantUser.tenant_id == tid,
                TenantUser.id == int(pmap.tenant_user_id),
            )
        )
        if not tu:
            pytest.skip("mapped tenant_user row missing")
        truthful = int(getattr(pu, "session_version", 1) or 1)
        corrupted = truthful + 10_000
        tu.session_version = corrupted
        await tdb.commit()
        break

    try:
        drift = await collect_tenant_auth_cutover_errors(tid)
        assert any("session_version drift" in e for e in drift), drift
    finally:
        async for tdb in open_tenant_session_by_id(tid):
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == tid,
                    TenantUser.id == int(pmap.tenant_user_id),
                )
            )
            if tu:
                tu.session_version = int(getattr(pu, "session_version", 1) or 1)
                await tdb.commit()
            break

    restored = await collect_tenant_auth_cutover_errors(tid)
    assert not restored, restored
