"""Startup enforcement and middleware behavior for TEST_BYPASS_AUTH / tenant shortcuts."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from app.core.config import (
    TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS,
    Settings,
    enforce_test_bypass_auth_policy,
)
from app.middleware.tenant_context import TenantContextMiddleware


@pytest.fixture
def clear_test_bypass(monkeypatch):
    monkeypatch.delenv("TEST_BYPASS_AUTH", raising=False)
    yield
    monkeypatch.delenv("TEST_BYPASS_AUTH", raising=False)


def test_enforce_rejects_test_bypass_on_non_allowlisted_env(monkeypatch, clear_test_bypass):
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    cfg = Settings(
        database_url="postgresql://u:p@h:5432/db",
        environment="production",
        allow_tenant_resolution_shortcuts=True,
    )
    with pytest.raises(RuntimeError, match="TEST_BYPASS_AUTH=1 is forbidden"):
        enforce_test_bypass_auth_policy(cfg)


def test_enforce_rejects_test_bypass_when_allow_flag_false(monkeypatch, clear_test_bypass):
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    cfg = Settings(
        database_url="postgresql://u:p@h:5432/db",
        environment="test",
        allow_tenant_resolution_shortcuts=False,
    )
    with pytest.raises(RuntimeError, match="ALLOW_TENANT_RESOLUTION_SHORTCUTS"):
        enforce_test_bypass_auth_policy(cfg)


def test_enforce_noop_when_test_bypass_not_set(monkeypatch, clear_test_bypass):
    monkeypatch.delenv("TEST_BYPASS_AUTH", raising=False)
    cfg = Settings(
        database_url="postgresql://u:p@h:5432/db",
        environment="production",
        allow_tenant_resolution_shortcuts=False,
    )
    enforce_test_bypass_auth_policy(cfg)


def test_enforce_accepts_test_bypass_in_safe_env_with_flag(monkeypatch, clear_test_bypass):
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    cfg = Settings(
        database_url="postgresql://u:p@h:5432/db",
        environment="test",
        allow_tenant_resolution_shortcuts=True,
    )
    enforce_test_bypass_auth_policy(cfg)


@pytest.mark.parametrize("env", sorted(TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS))
def test_enforce_accepts_each_safe_environment(monkeypatch, clear_test_bypass, env: str):
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    cfg = Settings(
        database_url="postgresql://u:p@h:5432/db",
        environment=env,
        allow_tenant_resolution_shortcuts=True,
    )
    enforce_test_bypass_auth_policy(cfg)


class _DummyApp:
    async def __call__(self, scope, receive, send):
        pass


def test_test_bypass_lookup_sqlalchemyerror_fails_closed_and_logs(caplog):
    caplog.set_level(logging.ERROR)

    middleware = TenantContextMiddleware(_DummyApp())

    async def call_next(_request: Request):
        from starlette.responses import Response

        return Response(b"ok")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/drivers",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)

    session_cm = MagicMock()

    async def session_aenter(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    async def session_aexit(*_args, **_kwargs):
        return False

    session_cm.__aenter__ = session_aenter
    session_cm.__aexit__ = session_aexit

    with (
        patch.dict("os.environ", {"TEST_BYPASS_AUTH": "1"}, clear=False),
        patch("app.middleware.tenant_context.settings") as mock_settings,
        patch("app.middleware.tenant_context.AsyncSessionLocal", return_value=session_cm),
        patch.object(middleware, "_slug_from_host", return_value="demo"),
        patch.object(
            middleware,
            "_resolve_tenant_from_request",
            new_callable=AsyncMock,
            return_value=(1, "demo"),
        ),
    ):
        mock_settings.allows_tenant_resolution_shortcuts = MagicMock(return_value=True)
        asyncio.run(middleware.dispatch(request, call_next))

    assert any(
        "test_bypass platform tenant lookup failed" in r.getMessage() for r in caplog.records
    )
