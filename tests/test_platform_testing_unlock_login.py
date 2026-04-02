"""Platform admin testing unlock-login: streak + tenant+email limiter reset."""

from __future__ import annotations

import types
from unittest.mock import AsyncMock

from app.core import config
from app.utils.auth_identity import normalize_auth_email
from app.utils.rate_limit import (
    clear_login_unlock_throttles_for_tenant_email,
    get_login_unlock_throttle_snapshot,
    login_per_tenant_email,
    login_tenant_email_bucket_key,
)


def test_unlock_login_clears_streak_and_tenant_email_rate_limits(monkeypatch):
    """Limiter: exhaust login_per_tenant_email then clear; endpoint: streak + throttle clear (mocked DB)."""
    tenant_id = 4242
    email_norm = normalize_auth_email("Demo.Unlock@example.com")
    key = login_tenant_email_bucket_key(tenant_id, email_norm)
    for _ in range(5):
        assert login_per_tenant_email.allow(key)
    assert not login_per_tenant_email.allow(key)
    assert login_per_tenant_email.is_at_or_over_limit(key)

    out = clear_login_unlock_throttles_for_tenant_email(tenant_id, email_norm)
    assert out["login_per_tenant_email"]["key"] == key
    assert out["login_per_tenant_email"]["had_entries"] is True

    assert not login_per_tenant_email.is_at_or_over_limit(key)
    assert login_per_tenant_email.allow(key)

    snap = get_login_unlock_throttle_snapshot(tenant_id, email_norm)
    assert snap["login_per_tenant_email"]["at_limit"] is False

    monkeypatch.setattr(config.settings, "platform_admin_api_key", "platform-test-key")

    async def fake_build_state(_tid: int, _en: str) -> dict:
        return {
            "password_fail_streak": {"has_active_window": False, "streak_count": 0},
            "tenant_email_rate_limits": {},
            "overall": {"all_clear_for_tenant_email_unlock_tool": True},
        }

    monkeypatch.setattr("app.services.sign_in_lock_state.build_sign_in_lock_state", fake_build_state)

    streak_calls: list[tuple[int, str]] = []

    async def fake_clear_streak(tid: int, en: str) -> int:
        streak_calls.append((tid, en))
        return 1

    monkeypatch.setattr("app.routers.platform_testing.clear_login_password_fail_streak", fake_clear_streak)
    monkeypatch.setattr(
        "app.routers.platform_testing.set_login_step_up_pending_after_unlock",
        AsyncMock(),
    )

    throttle_out = {
        "login_per_tenant_email": {"key": "k0", "had_entries": False},
        "login_step_up_issue_per_tenant_email": {"key": "k1", "had_entries": True},
        "login_step_up_verify_per_tenant_email": {"key": "k2", "had_entries": False},
    }
    monkeypatch.setattr(
        "app.routers.platform_testing.clear_login_unlock_throttles_for_tenant_email",
        lambda tid, en: throttle_out,
    )

    tenant_obj = types.SimpleNamespace(id=99, slug="demo-slug")

    class FakeSession:
        async def scalar(self, _stmt):
            return tenant_obj

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.routers.platform_testing import router

    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/platform/testing/unlock-login",
            json={"tenant_slug": "demo-slug", "email": "User@Example.com"},
            headers={"X-Platform-Admin-Key": "platform-test-key"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == 99
    assert body["tenant_slug"] == "demo-slug"
    assert body["email_norm"] == "user@example.com"
    assert body["cleared"]["platform_login_password_fail_streaks"]["rows_deleted"] == 1
    assert body["cleared"]["rate_limiters"] == throttle_out
    assert body["state_after"]["overall"]["all_clear_for_tenant_email_unlock_tool"] is True
    assert "login_per_ip" in body["note"].lower() or "IP" in body["note"]
    assert streak_calls == [(99, "user@example.com")]
