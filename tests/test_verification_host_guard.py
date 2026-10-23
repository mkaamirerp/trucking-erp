"""Unit tests for verification host guard (no Docker or production access)."""

from __future__ import annotations

import pytest

from app.core.verification_host_guard import (
    DISPOSABLE_CI_MARKER,
    VerificationHostDenied,
    assert_disposable_verification_host,
    assert_no_live_production_dump_source,
    assert_verification_auth_not_bypassed,
    collect_verification_denial_reasons,
    has_disposable_host_proof,
    refuse_live_demo_clone_ports,
)


@pytest.fixture
def disposable_ci(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("TRUCKERP_VERIFICATION_DISPOSABLE_CI", DISPOSABLE_CI_MARKER)


def test_production_instance_id_denied(disposable_ci, monkeypatch):
    monkeypatch.setattr(
        "app.core.verification_host_guard._fetch_ec2_instance_id",
        lambda: "i-0126f0dc65891ca63",
    )
    with pytest.raises(VerificationHostDenied):
        assert_disposable_verification_host()


def test_unknown_ec2_instance_denied_without_proof(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("TRUCKERP_VERIFICATION_DISPOSABLE_CI", raising=False)
    monkeypatch.setattr(
        "app.core.verification_host_guard._fetch_ec2_instance_id",
        lambda: "i-0unknownverificationhost",
    )
    monkeypatch.setattr(
        "app.core.verification_host_guard.read_verification_host_class_file",
        lambda: None,
    )
    assert not has_disposable_host_proof()
    with pytest.raises(VerificationHostDenied):
        assert_disposable_verification_host()


def test_bypass_env_var_denied(disposable_ci, monkeypatch):
    monkeypatch.setenv("TRUCKERP_SKIP_VERIFICATION_HOST_GUARD", "1")
    with pytest.raises(VerificationHostDenied):
        assert_disposable_verification_host()


def test_production_database_url_denied(disposable_ci, monkeypatch):
    monkeypatch.setenv("TENANT_DATABASE_URL", "postgresql://u:p@truckerp-postgres:5432/tenant_clone_20261019t001401z_ab12cd")
    with pytest.raises(VerificationHostDenied):
        assert_disposable_verification_host()


def test_live_tenant_demo_dump_denied():
    with pytest.raises(VerificationHostDenied):
        assert_no_live_production_dump_source("truckerp-postgres", "tenant_demo")


def test_certification_rejects_test_bypass_auth(monkeypatch):
    monkeypatch.setenv("TEST_BYPASS_AUTH", "1")
    with pytest.raises(VerificationHostDenied):
        assert_verification_auth_not_bypassed()


def test_refuse_live_demo_clone_ports(disposable_ci):
    class LiveSql:
        pass

    class LiveCommands:
        pass

    with pytest.raises(VerificationHostDenied, match="live execution is disabled"):
        refuse_live_demo_clone_ports(LiveSql(), LiveCommands())


def test_fake_sql_ports_allowed(disposable_ci):
    class FakeSql:
        pass

    class FakeCommands:
        pass

    refuse_live_demo_clone_ports(FakeSql(), FakeCommands())


def test_disposable_host_file_proof(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr("app.core.verification_host_guard._fetch_ec2_instance_id", lambda: None)
    monkeypatch.setattr(
        "app.core.verification_host_guard.read_verification_host_class_file",
        lambda: "disposable",
    )
    assert has_disposable_host_proof()
    assert collect_verification_denial_reasons() == []
