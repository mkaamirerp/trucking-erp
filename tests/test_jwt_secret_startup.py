"""Production/staging JWT_SECRET must fail closed; test env uses an explicit secret."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app.core.config import Settings, enforce_jwt_secret_policy
from app.utils.jwt_auth import TokenType, create_access_token, decode_token, extract_sv

DB = "postgresql://u:p@h:5432/db"
SCRIPT = Path("/home/admin/trucking_erp/scripts/start_api_with_ssm.sh")
STRONG = "n" * 32


def _cfg(**kwargs) -> Settings:
    base = dict(database_url=DB, postgres_admin_url=None)
    base.update(kwargs)
    return Settings(**base)


def _check_secrets(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--check-secrets-file", str(path)],
        capture_output=True,
        text=True,
        env={**os.environ, "SSM_ENV": "prod"},
        check=False,
    )


def _write_secrets(tmp_path: Path, extra: dict[str, str]) -> Path:
    rows = {
        "DATABASE_URL": "postgresql://u:p@h:5432/db",
        "POSTGRES_ADMIN_URL": "postgresql://u:p@h:5432/postgres",
        "POSTGRES_PASSWORD": "x",
        "LOGIN_TRUST_COOKIE_SECRET": "y" * 32,
        "ENVIRONMENT": "production",
    }
    rows.update(extra)
    p = tmp_path / "truckerp.env"
    p.write_text("".join(f"{k}={v}\n" for k, v in rows.items()), encoding="utf-8")
    return p


def test_production_missing_jwt_secret_fails():
    cfg = _cfg(environment="production", jwt_secret=None)
    with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
        enforce_jwt_secret_policy(cfg)


def test_production_dev_change_me_fails():
    cfg = _cfg(environment="production", jwt_secret="dev-change-me")
    with pytest.raises(RuntimeError, match="unsafe"):
        enforce_jwt_secret_policy(cfg)


def test_staging_placeholder_fails():
    cfg = _cfg(environment="staging", jwt_secret="DEV-CHANGE-ME")
    with pytest.raises(RuntimeError, match="unsafe"):
        enforce_jwt_secret_policy(cfg)


def test_production_obviously_weak_secret_fails():
    cfg = _cfg(environment="production", jwt_secret="short")
    with pytest.raises(RuntimeError, match="too short"):
        enforce_jwt_secret_policy(cfg)


def test_production_valid_secret_succeeds():
    cfg = _cfg(environment="production", jwt_secret=STRONG)
    enforce_jwt_secret_policy(cfg)


def test_test_environment_starts_with_explicit_secret():
    cfg = _cfg(environment="test", jwt_secret="test-only-jwt-secret-not-for-production")
    enforce_jwt_secret_policy(cfg)


def test_jwt_encode_raises_when_secret_missing(monkeypatch):
    monkeypatch.setattr("app.utils.jwt_auth.settings.jwt_secret", "")
    with pytest.raises(RuntimeError, match="JWT_SECRET is not configured"):
        create_access_token(user_id="u1", tenant_id=1, tenant_slug="demo", roles=[], sv=1)


def test_jwt_encode_decode_still_round_trips():
    token = create_access_token(
        user_id="u1",
        tenant_id=1,
        tenant_slug="demo",
        roles=["TENANT_ADMIN"],
        sv=7,
    )
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    assert extract_sv(payload) == 7
    assert payload["sub"] == "u1"


def test_ssm_check_missing_jwt_secret_fails(tmp_path: Path):
    secrets = _write_secrets(tmp_path, extra={})
    result = _check_secrets(secrets)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "JWT_SECRET" in combined
    assert "missing" in combined.lower() or "empty" in combined.lower()


def test_ssm_check_dev_change_me_fails_without_leaking_secret(tmp_path: Path):
    secrets = _write_secrets(tmp_path, extra={"JWT_SECRET": "dev-change-me"})
    result = _check_secrets(secrets)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "unsafe" in combined.lower()
    assert "dev-change-me" not in combined


def test_ssm_check_present_jwt_secret_passes_presence_gate(tmp_path: Path):
    secrets = _write_secrets(tmp_path, extra={"JWT_SECRET": STRONG})
    result = _check_secrets(secrets)
    assert result.returncode == 0, result.stdout + result.stderr
