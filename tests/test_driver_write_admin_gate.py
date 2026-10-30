"""Driver, driver-phone, legacy license-confirm and pay-profile writes require tenant admin.

Reads stay open to tenant members. Uses the integration tenant (pytest / tenant_pytest).
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")
MISSING = 987654321

WRITES = [
    ("POST", "/api/v1/drivers", {"first_name": "X"}),
    ("PATCH", f"/api/v1/drivers/{MISSING}", {"is_active": False}),
    ("PATCH", f"/api/v1/drivers/{MISSING}", {"termination_date": "2026-01-01"}),
    ("PATCH", f"/api/v1/drivers/{MISSING}", {"license_number": "Z1"}),
    ("POST", "/api/v1/driver-phones", {"driver_id": MISSING}),
    ("DELETE", f"/api/v1/driver-phones/{MISSING}", None),
    ("POST", f"/api/v1/driver-phones/{MISSING}/reactivate", None),
    ("POST", "/api/v1/onboarding/driver-license/confirm", {"driver_id": MISSING}),
    ("POST", "/api/v1/payroll/pay-profiles", {"driver_id": MISSING}),
    ("PATCH", f"/api/v1/payroll/pay-profiles/{MISSING}", {"notes": "x"}),
    ("POST", f"/api/v1/payroll/pay-profiles/{MISSING}/deactivate", None),
]


@pytest.fixture(autouse=True)
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        yield ac


def _headers() -> dict[str, str]:
    from tests.support.integration_isolation import integration_tenant_slug

    return {"host": f"{integration_tenant_slug()}.truckerp.me"}


async def _send(client: AsyncClient, method: str, path: str, body):
    kwargs = {"headers": _headers()}
    if body is not None:
        kwargs["json"] = body
    return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.parametrize("role", ["TENANT_MEMBER", "DISPATCHER", "READ_ONLY"])
async def test_non_admin_driver_writes_are_forbidden(client: AsyncClient, role: str) -> None:
    install_host_aligned_current_user_and_tenant(fastapi_app, role=role)
    try:
        for method, path, body in WRITES:
            resp = await _send(client, method, path, body)
            assert resp.status_code == 403, (role, method, path, resp.text)
            assert resp.json()["detail"]["code"] == "RBAC_FORBIDDEN"
        roster = await client.get("/api/v1/drivers", headers=_headers())
        assert roster.status_code == 200, roster.text
        phones = await client.get("/api/v1/driver-phones", headers=_headers())
        assert phones.status_code == 200, phones.text
    finally:
        clear_current_user_and_tenant_overrides(fastapi_app)


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"])
async def test_tenant_admin_driver_writes_pass_the_gate(client: AsyncClient, role: str) -> None:
    install_host_aligned_current_user_and_tenant(fastapi_app, role=role)
    try:
        for method, path, body in WRITES:
            resp = await _send(client, method, path, body)
            # Past the role gate: missing rows are 404, incomplete bodies are 400/422.
            assert resp.status_code in (400, 404, 422), (role, method, path, resp.status_code, resp.text)
    finally:
        clear_current_user_and_tenant_overrides(fastapi_app)
