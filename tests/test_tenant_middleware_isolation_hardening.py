"""Defense-in-depth: JWT tenant_id vs Host match + middleware membership for tenant_auth_mode.

Unit tests only (mocked platform/tenant sessions). No DB required.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.middleware.tenant_context import TenantContextMiddleware


class DummyApp:
    def __call__(self, scope, receive, send):
        raise RuntimeError("not used in tests")


def _make_request(
    *,
    host: str = "alpha.truckerp.me",
    path: str = "/api/v1/drivers",
    user_id: str | None = "user-a",
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"host", host.encode())],
        "query_string": b"",
    }
    request = Request(scope)
    if user_id is not None:
        request.state.user_id = user_id
    return request


def _platform_session(*scalar_results):
    """AsyncSessionLocal mock; scalar() returns results in order (tenant row, then membership)."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.scalar = AsyncMock(side_effect=list(scalar_results))
    return session


@pytest.fixture
def middleware() -> TenantContextMiddleware:
    return TenantContextMiddleware(DummyApp())


def test_jwt_tenant_a_host_tenant_a_allowed(middleware: TenantContextMiddleware) -> None:
    """JWT Tenant A + Host Tenant A → resolve succeeds (membership present)."""
    row = SimpleNamespace(
        id=10,
        slug="alpha",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="platform",
    )
    membership = SimpleNamespace(id=1, user_id="user-a", tenant_id=10, status="active")
    request = _make_request(host="alpha.truckerp.me", user_id="user-a")

    async def run() -> None:
        with patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory:
            session_factory.return_value = _platform_session(row, membership)
            tid, slug = await middleware._resolve_tenant_from_request(
                request, "/api/v1/drivers", jwt_tenant_id=10
            )
            assert tid == 10
            assert slug == "alpha"

    asyncio.run(run())


def test_jwt_tenant_a_host_tenant_b_forbidden_before_membership(
    middleware: TenantContextMiddleware,
) -> None:
    """JWT Tenant A + Host Tenant B → 403 before membership / tenant-DB open."""
    row = SimpleNamespace(
        id=20,
        slug="beta",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="platform",
    )
    request = _make_request(host="beta.truckerp.me", user_id="user-a")
    open_tenant = AsyncMock()
    session = _platform_session(row)

    async def run() -> None:
        with (
            patch("app.middleware.tenant_context.AsyncSessionLocal", return_value=session),
            patch(
                "app.middleware.tenant_context.open_tenant_session_by_id",
                open_tenant,
            ),
        ):
            with pytest.raises(HTTPException) as ei:
                await middleware._resolve_tenant_from_request(
                    request, "/api/v1/drivers", jwt_tenant_id=10
                )
            assert ei.value.status_code == 403
            detail = str(ei.value.detail).lower()
            assert "host" in detail or "workspace" in detail
            # Membership query never reached (only tenant registry lookup).
            assert session.scalar.await_count == 1
            open_tenant.assert_not_called()

    asyncio.run(run())


def test_user_without_membership_in_host_tenant_forbidden(
    middleware: TenantContextMiddleware,
) -> None:
    """Authenticated user with matching JWT but no membership → 403."""
    row = SimpleNamespace(
        id=10,
        slug="alpha",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="platform",
    )
    request = _make_request(host="alpha.truckerp.me", user_id="outsider")

    async def run() -> None:
        with patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory:
            session_factory.return_value = _platform_session(row, None)
            with pytest.raises(HTTPException) as ei:
                await middleware._resolve_tenant_from_request(
                    request, "/api/v1/drivers", jwt_tenant_id=10
                )
            assert ei.value.status_code == 403
            assert "access" in str(ei.value.detail).lower()

    asyncio.run(run())


def test_tenant_auth_mode_requires_workspace_member(
    middleware: TenantContextMiddleware,
) -> None:
    """tenant_auth_mode=tenant: no active TenantWorkspaceMember → 403 (no bypass)."""
    row = SimpleNamespace(
        id=10,
        slug="alpha",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="tenant",
    )
    request = _make_request(host="alpha.truckerp.me", user_id="42")

    tenant_session = AsyncMock()
    # TenantUser ACTIVE, then no workspace member
    tenant_session.scalar = AsyncMock(
        side_effect=[
            SimpleNamespace(id=42, tenant_id=10, status="ACTIVE"),
            None,
        ]
    )

    async def fake_open(_tenant_id: int):
        yield tenant_session

    async def run() -> None:
        with (
            patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory,
            patch(
                "app.middleware.tenant_context.open_tenant_session_by_id",
                side_effect=fake_open,
            ),
        ):
            session_factory.return_value = _platform_session(row)
            with pytest.raises(HTTPException) as ei:
                await middleware._resolve_tenant_from_request(
                    request, "/api/v1/drivers", jwt_tenant_id=10
                )
            assert ei.value.status_code == 403
            assert "access" in str(ei.value.detail).lower()

    asyncio.run(run())


def test_tenant_auth_mode_active_workspace_member_allowed(
    middleware: TenantContextMiddleware,
) -> None:
    """tenant_auth_mode=tenant: active TenantWorkspaceMember → allowed."""
    row = SimpleNamespace(
        id=10,
        slug="alpha",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="tenant",
    )
    request = _make_request(host="alpha.truckerp.me", user_id="42")

    tenant_session = AsyncMock()
    tenant_session.scalar = AsyncMock(
        side_effect=[
            SimpleNamespace(id=42, tenant_id=10, status="ACTIVE"),
            SimpleNamespace(id=1, tenant_user_id=42, status="active", role="TENANT_ADMIN"),
        ]
    )

    async def fake_open(_tenant_id: int):
        yield tenant_session

    async def run() -> None:
        with (
            patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory,
            patch(
                "app.middleware.tenant_context.open_tenant_session_by_id",
                side_effect=fake_open,
            ),
        ):
            session_factory.return_value = _platform_session(row)
            tid, slug = await middleware._resolve_tenant_from_request(
                request, "/api/v1/drivers", jwt_tenant_id=10
            )
            assert tid == 10
            assert slug == "alpha"

    asyncio.run(run())


def test_public_auth_skips_jwt_match_and_membership(
    middleware: TenantContextMiddleware,
) -> None:
    """Login path: leftover JWT for another tenant must not block Host resolution."""
    row = SimpleNamespace(
        id=20,
        slug="beta",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="platform",
    )
    request = _make_request(host="beta.truckerp.me", path="/api/v1/auth/login", user_id=None)

    async def run() -> None:
        with patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory:
            session_factory.return_value = _platform_session(row)
            tid, slug = await middleware._resolve_tenant_from_request(
                request, "/api/v1/auth/login", jwt_tenant_id=10
            )
            assert tid == 20
            assert slug == "beta"

    asyncio.run(run())


def test_applicant_path_skips_jwt_match_and_membership(
    middleware: TenantContextMiddleware,
) -> None:
    """Applicant invite routes resolve Host tenant without JWT membership gate."""
    row = SimpleNamespace(
        id=20,
        slug="beta",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="platform",
    )
    path = "/api/v1/driver-onboarding/applicant/application"
    request = _make_request(host="beta.truckerp.me", path=path, user_id=None)

    async def run() -> None:
        with patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory:
            session_factory.return_value = _platform_session(row)
            tid, slug = await middleware._resolve_tenant_from_request(
                request, path, jwt_tenant_id=10
            )
            assert tid == 20
            assert slug == "beta"

    asyncio.run(run())


def test_missing_jwt_tenant_id_does_not_fail_match_check(
    middleware: TenantContextMiddleware,
) -> None:
    """No JWT tenant_id claim → existing membership-only behavior (hardening #5 unchanged)."""
    row = SimpleNamespace(
        id=10,
        slug="alpha",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="platform",
    )
    membership = SimpleNamespace(id=1, user_id="user-a", tenant_id=10, status="active")
    request = _make_request(host="alpha.truckerp.me", user_id="user-a")

    async def run() -> None:
        with patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory:
            session_factory.return_value = _platform_session(row, membership)
            tid, slug = await middleware._resolve_tenant_from_request(
                request, "/api/v1/drivers", jwt_tenant_id=None
            )
            assert tid == 10
            assert slug == "alpha"

    asyncio.run(run())
