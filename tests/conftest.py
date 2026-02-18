"""Pytest fixtures for integration tests (signup → dashboard flow)."""
from __future__ import annotations

import os

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
