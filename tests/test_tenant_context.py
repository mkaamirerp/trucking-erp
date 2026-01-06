from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.middleware.tenant_context import TenantContextMiddleware


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/drivers",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


class DummyApp:
    def __call__(self, scope, receive, send):
        raise RuntimeError("not used in tests")


def test_resolve_tenant_blocks_when_not_ready():
    middleware = TenantContextMiddleware(DummyApp())
    request = _make_request({"X-Tenant-ID": "123"})

    tenant_row = SimpleNamespace(id=123, status="PROVISIONING", db_status="NOT_PROVISIONED")

    async def run() -> None:
        with patch("app.middleware.tenant_context.AsyncSessionLocal") as session_factory:
            session = AsyncMock()
            session.__aenter__.return_value = session
            session.scalar.return_value = tenant_row
            session_factory.return_value = session

            try:
                await middleware._resolve_tenant(request)
            except HTTPException as exc:
                assert exc.status_code == 403
                assert exc.detail == "Tenant not ready"
            else:
                raise AssertionError("Expected HTTPException for non-ready tenant")

    asyncio.run(run())
