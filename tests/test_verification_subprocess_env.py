"""Unit tests for sanitized verification subprocess environments."""

from __future__ import annotations

import os

import pytest

from app.core.verification_host_guard import VerificationHostDenied
from app.core.verification_subprocess_env import build_verification_subprocess_env


@pytest.fixture(autouse=True)
def _disposable_ci_marker(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("TRUCKERP_VERIFICATION_DISPOSABLE_CI", "workflow:verification-disposable")


def test_strips_parent_production_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@truckerp-postgres:5432/trucking_erp")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    env = build_verification_subprocess_env(
        {
            "TENANT_DATABASE_URL": "postgresql://verify:verify@localhost:5432/tenant_clone_20261019t001401z_ab12cd",
            "ALEMBIC_TENANT_DATABASE_URL": "postgresql+asyncpg://verify:verify@localhost:5432/tenant_clone_20261019t001401z_ab12cd",
        }
    )
    assert "DATABASE_URL" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "tenant_clone_20261019t001401z_ab12cd" in env["TENANT_DATABASE_URL"]


def test_certification_env_removes_test_bypass_auth(monkeypatch):
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    env = build_verification_subprocess_env(
        {
            "TENANT_DATABASE_URL": "postgresql://verify:verify@localhost:5432/tenant_clone_20261019t001401z_ab12cd",
        },
        allow_test_bypass_auth=False,
    )
    assert "TEST_BYPASS_AUTH" not in env


def test_rejects_production_url_in_updates():
    with pytest.raises(VerificationHostDenied):
        build_verification_subprocess_env(
            {"TENANT_DATABASE_URL": "postgresql://u:p@truckerp-postgres:5432/tenant_clone_20261019t001401z_ab12cd"}
        )
