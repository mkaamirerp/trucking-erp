"""Signed login trust cookie (UX only; no device registry)."""
from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.config import settings
from app.utils.login_trust_cookie import (
    COOKIE_NAME,
    create_login_trust_cookie_value,
    verify_login_trust_cookie,
)


def _request_with_cookie(value: str) -> Request:
    cookie_header = f"{COOKIE_NAME}={value}".encode("latin-1")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "headers": [(b"cookie", cookie_header)],
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _trust_secret_for_tests(monkeypatch):
    """Default: dedicated secret so create/verify work unless a test overrides."""
    monkeypatch.setattr(settings, "login_trust_cookie_secret", "pytest-login-trust-secret")
    monkeypatch.setattr(settings, "login_trust_cookie_dev_fallback_to_jwt", False)


def test_verify_rejects_wrong_tenant():
    v = create_login_trust_cookie_value(tenant_id=7)
    assert v is not None
    req = _request_with_cookie(v)
    assert verify_login_trust_cookie(req, 8) is False
    assert verify_login_trust_cookie(req, 7) is True


def test_verify_rejects_tampered_payload(monkeypatch):
    monkeypatch.setattr(settings, "login_trust_cookie_secret", "unit-test-trust-secret")
    v = create_login_trust_cookie_value(tenant_id=1)
    assert v is not None
    parts = v.split(".", 1)
    tampered = parts[0][:-2] + "xx" + "." + parts[1]
    req = _request_with_cookie(tampered)
    assert verify_login_trust_cookie(req, 1) is False


def test_verify_rejects_missing_cookie():
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "headers": [],
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    assert verify_login_trust_cookie(Request(scope), 1) is False


def test_production_missing_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "login_trust_cookie_secret", None)
    monkeypatch.setattr(settings, "login_trust_cookie_dev_fallback_to_jwt", True)
    monkeypatch.setattr(settings, "jwt_secret", "jwt-must-not-be-used")
    assert create_login_trust_cookie_value(1) is None
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "headers": [(b"cookie", b"trk_login_trust=fake.fake")],
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    assert verify_login_trust_cookie(Request(scope), 1) is False


def test_staging_missing_secret_no_jwt_fallback(monkeypatch):
    monkeypatch.setattr(settings, "environment", "staging")
    monkeypatch.setattr(settings, "login_trust_cookie_secret", None)
    monkeypatch.setattr(settings, "login_trust_cookie_dev_fallback_to_jwt", True)
    monkeypatch.setattr(settings, "jwt_secret", "jwt-x")
    assert create_login_trust_cookie_value(1) is None


def test_dev_explicit_jwt_fallback_only_when_flag(monkeypatch):
    monkeypatch.setattr(settings, "environment", "dev")
    monkeypatch.setattr(settings, "login_trust_cookie_secret", None)
    monkeypatch.setattr(settings, "login_trust_cookie_dev_fallback_to_jwt", True)
    monkeypatch.setattr(settings, "jwt_secret", "jwt-dev-only")
    v = create_login_trust_cookie_value(3)
    assert v is not None
    req = _request_with_cookie(v)
    assert verify_login_trust_cookie(req, 3) is True


def test_dev_no_fallback_without_flag(monkeypatch):
    monkeypatch.setattr(settings, "environment", "dev")
    monkeypatch.setattr(settings, "login_trust_cookie_secret", None)
    monkeypatch.setattr(settings, "login_trust_cookie_dev_fallback_to_jwt", False)
    monkeypatch.setattr(settings, "jwt_secret", "jwt-unused")
    assert create_login_trust_cookie_value(1) is None
