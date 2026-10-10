"""Issue 3 — generic Load PATCH cannot transition draft→ready; mark-ready endpoint is sole authority."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.trip_dispatch import (
    LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED,
    LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT,
)
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

AUTH_HEADERS = {"host": "pytest.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
REQUIRES_INTEGRATION = _PLACEHOLDER_PLATFORM_DB or not (
    os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
)

_VALID_STOPS = [
    {"stop_type": "PICKUP", "sequence": 0, "city": "Austin", "state_or_province": "TX"},
    {"stop_type": "DROP", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
]


def _detail_code(payload: dict) -> str | None:
    d = payload.get("detail")
    return d.get("code") if isinstance(d, dict) else None


@pytest.fixture
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


async def _new_draft(client: AsyncClient, tag: str, **extra) -> dict:
    r = await client.post(
        "/api/v1/loads",
        headers=AUTH_HEADERS,
        json={"status": "draft", "load_number": f"{tag}-{uuid.uuid4().hex[:8]}", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.skipif(REQUIRES_INTEGRATION, reason="integration tenant DB required")
class TestMarkReadyGateIssue3Http:
    async def test_patch_draft_to_ready_rejected_preserves_status_and_cv(self, client, override_auth_tenant) -> None:
        created = await _new_draft(
            client,
            "I3-PATCH",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-1",
            stops=_VALID_STOPS,
        )
        cv_before = created["concurrency_version"]
        r = await client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={"status": "ready", "expected_concurrency_version": cv_before},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT
        snap = (await client.get(f"/api/v1/loads/{created['id']}", headers=AUTH_HEADERS)).json()
        assert snap["status"] == "draft"
        assert snap["concurrency_version"] == cv_before

    async def test_patch_ready_without_prerequisites_still_rejected(self, client, override_auth_tenant) -> None:
        created = await _new_draft(client, "I3-NOPREQ")
        r = await client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={"status": "ready", "expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT

    async def test_commercial_patch_omitting_status_succeeds(self, client, override_auth_tenant) -> None:
        created = await _new_draft(client, "I3-COMM")
        r = await client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={
                "commodity": "Widgets",
                "expected_concurrency_version": created["concurrency_version"],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["commodity"] == "Widgets"
        assert r.json()["status"] == "draft"

    async def test_patch_explicit_ready_unchanged_on_ready_load(self, client, override_auth_tenant) -> None:
        created = await _new_draft(
            client,
            "I3-READY",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-2",
            stops=_VALID_STOPS,
        )
        mr = await client.post(
            f"/api/v1/loads/{created['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": created["concurrency_version"]},
        )
        assert mr.status_code == 200, mr.text
        ready = mr.json()
        r = await client.patch(
            f"/api/v1/loads/{ready['id']}",
            headers=AUTH_HEADERS,
            json={
                "status": "ready",
                "internal_notes": "still ready",
                "expected_concurrency_version": ready["concurrency_version"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ready"
        assert body["internal_notes"] == "still ready"

    async def test_mark_ready_success_with_prerequisites(self, client, override_auth_tenant) -> None:
        created = await _new_draft(
            client,
            "I3-MR-OK",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-3",
            stops=_VALID_STOPS,
        )
        r = await client.post(
            f"/api/v1/loads/{created['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ready"

    async def test_mark_ready_rejects_missing_prerequisites(self, client, override_auth_tenant) -> None:
        created = await _new_draft(client, "I3-MR-BAD")
        r = await client.post(
            f"/api/v1/loads/{created['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 400

    async def test_post_legacy_status_still_rejected(self, client, override_auth_tenant) -> None:
        ln = f"I3-LEG-{uuid.uuid4().hex[:8]}"
        r = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "dispatched", "load_number": ln},
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
