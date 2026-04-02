"""Platform /api/v1/platform/* must never return data without a valid admin key."""

from __future__ import annotations

from app.core import config


def test_platform_tenants_503_when_admin_key_not_configured(client, monkeypatch):
    monkeypatch.setattr(config.settings, "platform_admin_api_key", None)
    r = client.get("/api/v1/platform/tenants")
    assert r.status_code == 503
    assert "PLATFORM_ADMIN_API_KEY" in r.json().get("detail", "")


def test_platform_tenants_401_without_header_when_key_configured(client, monkeypatch):
    monkeypatch.setattr(config.settings, "platform_admin_api_key", "test-platform-admin-secret")
    r = client.get("/api/v1/platform/tenants")
    assert r.status_code == 401
    assert r.json().get("detail") == "Unauthorized"


def test_platform_tenants_401_wrong_key_when_key_configured(client, monkeypatch):
    monkeypatch.setattr(config.settings, "platform_admin_api_key", "right-key")
    r = client.get("/api/v1/platform/tenants", headers={"X-Platform-Admin-Key": "wrong-key"})
    assert r.status_code == 401


def test_platform_tenants_accepts_x_truckerp_platform_admin_key(client, monkeypatch):
    monkeypatch.setattr(config.settings, "platform_admin_api_key", "browser-key")
    r = client.get("/api/v1/platform/tenants", headers={"X-TruckERP-Platform-Admin-Key": "browser-key"})
    assert r.status_code != 401
    assert r.status_code != 503
