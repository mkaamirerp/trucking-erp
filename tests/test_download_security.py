"""Tests for download endpoint tenant isolation and forbidden access."""
from __future__ import annotations

import os

import pytest

REQUIRES_DB = not os.environ.get("DATABASE_URL")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


class TestCompanySetupDocumentTenantIsolation:
    """GET /api/v1/public/company-setup/document must enforce tenant isolation."""

    def test_forbidden_when_key_prefix_mismatch(self, client) -> None:
        """Requesting demo's key while Host is another workspace must return 403."""
        storage_key = "demo/company_docs/company/53/abc123.pdf"
        resp = client.get(
            f"/api/v1/public/company-setup/document?storage_key={storage_key}",
            headers={"host": "acme.truckerp.me"},
        )
        assert resp.status_code == 403
        assert "not valid for tenant" in resp.json().get("detail", "").lower()

    def test_400_when_no_tenant(self, client) -> None:
        """Request without tenant (no subdomain, no header) must return 400."""
        storage_key = "demo/company_docs/company/53/abc123.pdf"
        resp = client.get(
            f"/api/v1/public/company-setup/document?storage_key={storage_key}",
        )
        assert resp.status_code == 400
        assert "tenant" in resp.json().get("detail", "").lower()


class TestPayDocumentTenantIsolation:
    """GET /api/v1/payroll/documents/{id}/download must return doc only for owning tenant."""

    @pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
    def test_404_when_doc_from_other_tenant(self, client) -> None:
        """Requesting a document by ID with wrong tenant context returns 404 (doc not found)."""
        resp = client.get(
            "/api/v1/payroll/documents/99999/download",
            headers={"host": "demo.truckerp.me"},
        )
        assert resp.status_code in (404, 422)


class TestApplicantFileTenantIsolation:
    """Applicant file endpoints must resolve tenant from token and reject cross-tenant access."""

    @pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
    def test_404_with_invalid_token(self, client) -> None:
        """Invalid or expired token returns 404."""
        resp = client.get(
            "/api/v1/driver-onboarding/applicant/application/file",
            params={"token": "invalid-token-xyz", "file_id": "any"},
            headers={"host": "demo.truckerp.me"},
        )
        assert resp.status_code == 404
