"""Settings: dev-only tenant resolution shortcuts never apply in production/staging."""
from __future__ import annotations

from app.core.config import Settings


def test_allows_dev_tenant_resolution_shortcuts() -> None:
    url = "postgresql://u:p@db.example.com:5432/trucking_erp"
    assert Settings(database_url=url, environment="dev").allows_dev_tenant_resolution_shortcuts() is True
    assert Settings(database_url=url, environment="development").allows_dev_tenant_resolution_shortcuts() is True
    assert Settings(database_url=url, environment="production").allows_dev_tenant_resolution_shortcuts() is False
    assert Settings(database_url=url, environment="prod").allows_dev_tenant_resolution_shortcuts() is False
    assert Settings(database_url=url, environment="staging").allows_dev_tenant_resolution_shortcuts() is False
    assert Settings(database_url=url, environment="stg").allows_dev_tenant_resolution_shortcuts() is False
