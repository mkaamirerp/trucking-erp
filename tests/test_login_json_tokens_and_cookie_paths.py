"""Login success JSON must not expose JWTs; cookies remain the session channel."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.responses import Response

from app.routers.auth import LoginRequest, _cookie_params, login
from app.utils.jwt_auth import TokenType
from tests.support.auth_cookies import cookie_path_from_response, cookie_value_from_response


def _tenant():
    t = SimpleNamespace(
        id=1,
        slug="demo",
        name="Demo",
        status="ACTIVE",
        db_status="READY",
        tenant_auth_mode="platform",
        company_profile=None,
    )
    return t


def _platform_user():
    u = SimpleNamespace(
        id="user-uuid-1",
        email="owner@example.com",
        status="ACTIVE",
        password_hash="hashed",
        session_version=3,
        first_name="A",
        last_name="B",
        is_email_verified=True,
    )
    return u


@pytest.mark.asyncio
async def test_login_success_sets_cookies_and_omits_tokens_from_json():
    tenant = _tenant()
    user = _platform_user()
    membership = SimpleNamespace(role="TENANT_OWNER")
    tm = SimpleNamespace(status="active")

    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[tenant, user, membership, tm])

    request = MagicMock()
    request.state = SimpleNamespace(tenant_id=1, tenant_slug="demo")
    request.url = SimpleNamespace(scheme="https", hostname="demo.truckerp.me")
    response = Response()
    payload = LoginRequest(email="owner@example.com", password="password123456")

    with (
        patch("app.routers.auth.rate_limit_login_ip", AsyncMock()),
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch("app.routers.auth.verify_login_trust_cookie", return_value=False),
        patch("app.routers.auth.assert_login_human_verification_if_armed", AsyncMock()),
        patch("app.routers.auth.login_step_up_challenge_gate_after_password", AsyncMock(return_value=None)),
        patch("app.routers.auth.verify_password", return_value=True),
        patch("app.routers.auth.clear_login_password_fail_streak", AsyncMock(return_value=0)),
        patch("app.routers.auth.tenant_uses_tenant_db_auth", return_value=False),
    ):
        body = await login(payload, request, response, db)

    assert body.get("ok") is True
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert cookie_value_from_response(response, "access_token")
    assert cookie_value_from_response(response, "refresh_token")
    assert cookie_path_from_response(response, "refresh_token") == "/api/v1/auth/refresh"
    assert cookie_path_from_response(response, "access_token") in ("/", None)


def test_auth_refresh_cookie_params_path():
    assert _cookie_params(TokenType.REFRESH)["path"] == "/api/v1/auth/refresh"
    assert _cookie_params(TokenType.ACCESS)["path"] == "/"
