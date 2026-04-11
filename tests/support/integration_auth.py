"""
FastAPI dependency_overrides for integration tests only.

What this does:
  • `install_host_aligned_*` — fake user + require_tenant track `request.state.tenant_id` from Host + TEST_BYPASS.
    Matches how entitlements use `CurrentUser.tenant_id` with the same workspace the middleware resolved.

What this does NOT do:
  • Replace JWT/session logic, RBAC, or subscription rules — it bypasses auth and must be paired with
    `TEST_BYPASS_AUTH=1`, `ENVIRONMENT=test`, and `ALLOW_TENANT_RESOLUTION_SHORTCUTS=true` where required.

Do not add helpers here that encode product behavior; keep overrides thin.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from fastapi import Request

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant


def install_host_aligned_current_user_and_tenant(app: Any, *, role: str = "TENANT_ADMIN") -> None:
    """
    Overrides get_current_user + require_tenant for TEST_BYPASS + subdomain Host (e.g. demo).

    Entitlement deps (admin_sensitive, email_inbox, …) read CurrentUser.tenant_id — it must match
    the subscription row for the same workspace as request.state.tenant_id.
    """

    async def _fake_current_user(request: Request) -> MagicMock:
        tid = getattr(request.state, "tenant_id", None)
        if tid is None:
            raise RuntimeError(
                "request.state.tenant_id missing — use TEST_BYPASS_AUTH=1 and a tenant Host header (e.g. demo.truckerp.me)"
            )
        fake_user = MagicMock()
        fake_user.user_id = "test-user-id"
        fake_user.email = "test@example.com"
        fake_user.tenant_id = int(tid)
        fake_user.role = role
        # Admin onboarding routes (e.g. PersonApplication approve) persist reviewed_by / approved_by.
        fake_user.member_id = 1
        return fake_user

    def _tenant_from_request(request: Request) -> int:
        tid = getattr(request.state, "tenant_id", None)
        if tid is None:
            raise RuntimeError(
                "request.state.tenant_id missing — use TEST_BYPASS_AUTH=1 and a tenant Host header"
            )
        return int(tid)

    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[require_tenant] = _tenant_from_request


def install_mutable_tenant_current_user_and_tenant(
    app: Any,
    holder: dict[str, int],
    *,
    role: str = "TENANT_ADMIN",
    user_id: str = "test-user-id",
    email: str = "test@example.com",
) -> None:
    """
    Same as host-aligned, but tenant id comes from holder[\"tenant_id\"] (cross-tenant isolation tests).

    Request Host can stay demo; dependency layer simulates a different workspace id.
    """

    async def _fake_current_user(request: Request) -> MagicMock:
        tid = int(holder["tenant_id"])
        fake_user = MagicMock()
        fake_user.user_id = user_id
        fake_user.email = email
        fake_user.tenant_id = tid
        fake_user.role = role
        fake_user.member_id = 1
        return fake_user

    def _tenant_from_holder(request: Request) -> int:  # noqa: ARG001
        return int(holder["tenant_id"])

    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[require_tenant] = _tenant_from_holder


def clear_current_user_and_tenant_overrides(app: Any) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant, None)
