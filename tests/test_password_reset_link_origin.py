"""Password-reset emails must use a server-built origin, never a caller URL."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.routers.auth import ForgotPasswordRequest, _hash_reset_token, forgot_password
from app.services.password_reset_links import build_password_reset_link, password_reset_public_origin


def _cfg(**kwargs) -> Settings:
    base = dict(
        database_url="postgresql://u:p@h:5432/db",
        postgres_admin_url=None,
        jwt_secret="test-only-jwt-secret-not-for-production",
        base_domain="truckerp.me",
        environment="test",
    )
    base.update(kwargs)
    return Settings(**base)


def test_attacker_origin_is_not_used_by_builder():
    cfg = _cfg(environment="production", jwt_secret="a" * 32)
    link = build_password_reset_link(
        raw_token="tok123",
        tenant_slug=None,
        cfg=cfg,
    )
    assert link == "https://truckerp.me/reset-password?token=tok123"
    assert "evil" not in link


def test_production_workspace_link_uses_trusted_subdomain():
    cfg = _cfg(environment="production", jwt_secret="a" * 32)
    assert password_reset_public_origin(tenant_slug="demo", cfg=cfg) == "https://demo.truckerp.me"
    link = build_password_reset_link(raw_token="abc", tenant_slug="demo", cfg=cfg)
    assert link == "https://demo.truckerp.me/reset-password?token=abc"


def test_production_ignores_password_reset_public_origin_override():
    cfg = _cfg(
        environment="production",
        jwt_secret="a" * 32,
        password_reset_public_origin="https://evil.example",
    )
    assert password_reset_public_origin(tenant_slug=None, cfg=cfg) == "https://truckerp.me"
    assert password_reset_public_origin(tenant_slug="acme", cfg=cfg) == "https://acme.truckerp.me"


def test_test_env_override_is_deterministic():
    cfg = _cfg(environment="test", password_reset_public_origin="http://127.0.0.1:5173/ignored-path")
    assert password_reset_public_origin(tenant_slug="demo", cfg=cfg) == "http://127.0.0.1:5173"
    link = build_password_reset_link(raw_token="local-token", tenant_slug="demo", cfg=cfg)
    assert link == "http://127.0.0.1:5173/reset-password?token=local-token"


def test_unsafe_slug_does_not_change_apex_origin():
    cfg = _cfg(environment="production", jwt_secret="a" * 32)
    assert password_reset_public_origin(tenant_slug="evil.example", cfg=cfg) == "https://truckerp.me"
    assert password_reset_public_origin(tenant_slug="www", cfg=cfg) == "https://truckerp.me"


def test_forgot_password_schema_drops_caller_reset_base_url():
    payload = ForgotPasswordRequest.model_validate(
        {"email": "owner@example.com", "reset_base_url": "https://evil.example"}
    )
    dumped = payload.model_dump()
    assert dumped["email"] == "owner@example.com"
    assert "reset_base_url" not in dumped


@pytest.mark.asyncio
async def test_forgot_password_email_ignores_attacker_reset_base_url_and_keeps_token():
    user = SimpleNamespace(
        id="user-1",
        email="owner@example.com",
        password_reset_token_hash=None,
        password_reset_expires_at=None,
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=user)
    db.commit = AsyncMock()
    request = MagicMock()
    request.state = SimpleNamespace(tenant_id=None, tenant_slug=None)
    captured: dict = {}
    raw = "fixed_reset_token_aaaaaaaaaaaaaaaa"

    async def fake_send(*, to, reset_link, expires_minutes=60):  # noqa: ARG001
        captured["to"] = to
        captured["reset_link"] = reset_link

    payload = ForgotPasswordRequest.model_validate(
        {"email": "owner@example.com", "reset_base_url": "https://evil.example"}
    )
    with (
        patch("app.routers.auth.rate_limit_forgot_password", AsyncMock()),
        patch("app.routers.auth.send_password_reset_email", fake_send),
        patch("app.routers.auth.secrets.token_urlsafe", return_value=raw),
        patch("app.services.password_reset_links.settings", _cfg(environment="production", jwt_secret="a" * 32)),
        patch("app.routers.auth.settings") as auth_settings,
    ):
        auth_settings.secure_cookies = True
        body = await forgot_password(payload, request, db)

    assert body["ok"] is True
    assert "evil.example" not in captured["reset_link"]
    assert captured["reset_link"] == f"https://truckerp.me/reset-password?token={raw}"
    assert user.password_reset_token_hash == _hash_reset_token(raw)
    assert user.password_reset_expires_at is not None
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_forgot_password_workspace_host_uses_tenant_slug_origin():
    tenant_row = SimpleNamespace(id=1, tenant_auth_mode="platform")
    user = SimpleNamespace(
        id="user-1",
        email="owner@example.com",
        password_reset_token_hash=None,
        password_reset_expires_at=None,
    )
    membership = SimpleNamespace(id=9)
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[tenant_row, user, membership, None])
    db.commit = AsyncMock()
    request = MagicMock()
    request.state = SimpleNamespace(tenant_id=1, tenant_slug="demo")
    captured: dict = {}

    async def fake_send(*, to, reset_link, expires_minutes=60):  # noqa: ARG001
        captured["reset_link"] = reset_link

    payload = ForgotPasswordRequest(email="owner@example.com")
    with (
        patch("app.routers.auth.rate_limit_forgot_password", AsyncMock()),
        patch("app.routers.auth.rate_limit_forgot_password_respects_login_tenant_bucket", AsyncMock()),
        patch("app.routers.auth.tenant_uses_tenant_db_auth", return_value=False),
        patch("app.routers.auth.send_password_reset_email", fake_send),
        patch("app.routers.auth.secrets.token_urlsafe", return_value="ws-token"),
        patch("app.services.password_reset_links.settings", _cfg(environment="production", jwt_secret="a" * 32)),
        patch("app.routers.auth.settings") as auth_settings,
    ):
        auth_settings.secure_cookies = True
        await forgot_password(payload, request, db)

    assert captured["reset_link"] == "https://demo.truckerp.me/reset-password?token=ws-token"


@pytest.mark.asyncio
async def test_forgot_password_tenant_auth_still_mirrors_token_and_uses_workspace_origin():
    tenant_row = SimpleNamespace(id=7, tenant_auth_mode="tenant")
    tu = SimpleNamespace(id=101, tenant_id=7)
    twm = SimpleNamespace(id=1)
    pmap = SimpleNamespace(platform_user_id="plat-1")
    user = SimpleNamespace(id="plat-1", email="owner@example.com")
    tdb = MagicMock()
    tdb.scalar = AsyncMock(side_effect=[tu, twm])
    tdb.commit = AsyncMock()

    async def fake_open(_tid: int):
        yield tdb

    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[tenant_row, pmap, user])
    request = MagicMock()
    request.state = SimpleNamespace(tenant_id=7, tenant_slug="acme")
    captured: dict = {}
    raw = "tenant-auth-reset-token"

    async def fake_send(*, to, reset_link, expires_minutes=60):  # noqa: ARG001
        captured["reset_link"] = reset_link

    payload = ForgotPasswordRequest.model_validate(
        {"email": "owner@example.com", "reset_base_url": "https://evil.example"}
    )
    with (
        patch("app.routers.auth.rate_limit_forgot_password", AsyncMock()),
        patch("app.routers.auth.rate_limit_forgot_password_respects_login_tenant_bucket", AsyncMock()),
        patch("app.routers.auth.tenant_uses_tenant_db_auth", return_value=True),
        patch("app.routers.auth.open_tenant_session_by_id", fake_open),
        patch("app.routers.auth.mirror_reset_tokens_to_platform", AsyncMock()) as mirror,
        patch("app.routers.auth.send_password_reset_email", fake_send),
        patch("app.routers.auth.secrets.token_urlsafe", return_value=raw),
        patch("app.services.password_reset_links.settings", _cfg(environment="production", jwt_secret="a" * 32)),
        patch("app.routers.auth.settings") as auth_settings,
    ):
        auth_settings.secure_cookies = True
        await forgot_password(payload, request, db)

    assert captured["reset_link"] == f"https://acme.truckerp.me/reset-password?token={raw}"
    assert "evil.example" not in captured["reset_link"]
    assert tu.password_reset_token_hash == _hash_reset_token(raw)
    mirror.assert_awaited()
    tdb.commit.assert_awaited()
