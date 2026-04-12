"""Pytest fixtures for integration tests (signup → dashboard flow)."""
from __future__ import annotations

import os

# Before Settings() is imported: force safe test env + shortcuts (matches app.core.config policy).
# Do not use setdefault: docker/CI often preloads truckerp.env with ENVIRONMENT=production; setdefault
# would leave production and break TEST_BYPASS_AUTH platform tenant lookup in middleware.
os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_TENANT_RESOLUTION_SHORTCUTS"] = "true"
# Settings() validates DATABASE_URL at import; many unit tests import app modules without a real DB.
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

import pytest

# Skip signup-to-dashboard flow tests if no database (CI may run without Postgres)
REQUIRES_DB = not os.environ.get("DATABASE_URL")


@pytest.fixture(scope="module")
def app():
    """FastAPI app for TestClient (lazy import so skipped tests don't load Settings)."""
    from app.main import app as _app
    return _app


@pytest.fixture(scope="module")
def client(app):
    """TestClient for the app."""
    from fastapi.testclient import TestClient
    return TestClient(app)
