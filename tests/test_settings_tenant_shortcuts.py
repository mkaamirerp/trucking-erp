"""Tenant resolution shortcuts: explicit allow flag + environment allowlist only."""
from __future__ import annotations

from app.core.config import (
    TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS,
    Settings,
)


def _url() -> str:
    return "postgresql://u:p@db.example.com:5432/trucking_erp"


def test_allows_tenant_resolution_shortcuts_requires_flag_and_allowlisted_env() -> None:
    url = _url()
    base = dict(database_url=url, allow_tenant_resolution_shortcuts=True)
    for env in TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS:
        assert Settings(**base, environment=env).allows_tenant_resolution_shortcuts() is True

    assert Settings(database_url=url, environment="test", allow_tenant_resolution_shortcuts=False).allows_tenant_resolution_shortcuts() is False

    for bad in ("production", "prod", "staging", "uat", "preprod", "demo", ""):
        assert (
            Settings(database_url=url, environment=bad, allow_tenant_resolution_shortcuts=True).allows_tenant_resolution_shortcuts()
            is False
        )


def test_shortcuts_disallowed_for_unknown_env_even_with_flag() -> None:
    url = _url()
    assert (
        Settings(
            database_url=url,
            environment="prodcution",
            allow_tenant_resolution_shortcuts=True,
        ).allows_tenant_resolution_shortcuts()
        is False
    )
