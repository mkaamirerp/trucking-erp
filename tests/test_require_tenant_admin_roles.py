"""Canonical tenant-admin gate used by require_tenant_admin."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.deps.admin import TENANT_ADMIN_ROLES, is_tenant_admin
from app.dependencies.authz import require_tenant_admin


@pytest.mark.parametrize("role", sorted(TENANT_ADMIN_ROLES))
@pytest.mark.asyncio
async def test_canonical_admin_roles_are_allowed(role: str):
    assert is_tenant_admin(role) is True
    await require_tenant_admin(SimpleNamespace(role=role))  # type: ignore[arg-type]


@pytest.mark.parametrize("role", ["TENANT_OWNER", "TENANT_ADMIN", "OWNER", "ADMIN"])
@pytest.mark.asyncio
async def test_named_admin_roles_allowed(role: str):
    await require_tenant_admin(SimpleNamespace(role=role))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_tenant_member_denied():
    with pytest.raises(HTTPException) as exc:
        await require_tenant_admin(SimpleNamespace(role="TENANT_MEMBER"))  # type: ignore[arg-type]
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "RBAC_FORBIDDEN"


@pytest.mark.parametrize("role", [None, "", "UNKNOWN", "dispatcher"])
@pytest.mark.asyncio
async def test_missing_or_unknown_role_denied(role):
    assert is_tenant_admin(role) is False
    with pytest.raises(HTTPException) as exc:
        await require_tenant_admin(SimpleNamespace(role=role))  # type: ignore[arg-type]
    assert exc.value.status_code == 403
