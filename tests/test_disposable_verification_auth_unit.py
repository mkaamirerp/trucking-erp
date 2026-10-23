"""Unit tests for disposable verification authorization helpers (no database)."""

from __future__ import annotations

import pytest

from app.core.verification_host_guard import VerificationHostDenied
from tests.support.disposable_verification_auth import (
    CERTIFICATION_AUTH_MODE,
    build_certification_bearer_headers,
    require_certification_auth_mode,
)


def test_require_certification_auth_mode_rejects_bypass(monkeypatch):
    monkeypatch.setenv("TRUCKERP_VERIFICATION_AUTH_MODE", CERTIFICATION_AUTH_MODE)
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    with pytest.raises(VerificationHostDenied):
        require_certification_auth_mode()


def test_require_certification_auth_mode_requires_marker(monkeypatch):
    monkeypatch.delenv("TEST_BYPASS_AUTH", raising=False)
    monkeypatch.setenv("TRUCKERP_VERIFICATION_AUTH_MODE", "service")
    with pytest.raises(VerificationHostDenied):
        require_certification_auth_mode()


def test_build_certification_bearer_headers(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    headers = build_certification_bearer_headers(
        user_id="user-1",
        tenant_id=42,
        email="verification-admin@example.test",
    )
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["host"] == "pytest.truckerp.me"
