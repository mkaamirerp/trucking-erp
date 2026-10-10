"""Issue 3 — generic Load PATCH cannot transition draft→ready; mark-ready endpoint is sole authority.

HTTP regression tests mutate only the dedicated integration tenant (tenant_pytest) and
always delete loads they create, including after assertion failures.
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.trip_dispatch import (
    LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED,
    LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT,
)
from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError, integration_tenant_db_name
from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import (
    AUTH_HEADERS,
    assert_mutating_integration_allowed,
    database_name_from_url,
    require_integration_tenant_database_url,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

_VALID_STOPS = [
    {"stop_type": "PICKUP", "sequence": 0, "city": "Austin", "state_or_province": "TX"},
    {"stop_type": "DROP", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
]

# Populated when HTTP fixtures run (evidence for review reports).
ISSUE3_LAST_ISOLATION_EVIDENCE: dict[str, str | int] = {}


def _detail_code(payload: dict) -> str | None:
    d = payload.get("detail")
    return d.get("code") if isinstance(d, dict) else None


def _integration_db_configured() -> bool:
    try:
        require_integration_tenant_database_url(context="issue3_mark_ready_gate_precheck")
        return True
    except IntegrationIsolationError:
        return False


_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
SKIP_ISSUE3_HTTP = _PLACEHOLDER_PLATFORM_DB or not _integration_db_configured()


async def _cleanup_load_rows(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context="issue3_cleanup_load")
    await db.execute(
        text(
            "delete from audit_events where tenant_id=:t and entity_type='load' and entity_id=:e"
        ),
        {"t": tenant_id, "e": str(load_id)},
    )
    await db.execute(
        text("delete from load_stops where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from load_notes where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.commit()


async def _assert_load_absent(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    n = await db.scalar(
        text("select count(*) from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    assert int(n or 0) == 0, f"loads row still present after cleanup (tenant_id={tenant_id}, id={load_id})"


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


@pytest.fixture
def issue3_integration_gate():
    """Hard gate: refuse to run HTTP mutations without tenant_pytest (or configured integration DB)."""
    try:
        tenant_url = require_integration_tenant_database_url(context="issue3_mark_ready_gate")
    except IntegrationIsolationError as exc:
        pytest.skip(f"Issue 3 HTTP tests require isolated tenant DB: {exc}")
    db_name = database_name_from_url(tenant_url)
    expected = integration_tenant_db_name()
    if db_name != expected:
        pytest.skip(
            f"Issue 3 HTTP tests require database {expected!r}, got {db_name!r} "
            f"(TENANT_DATABASE_URL path segment)."
        )
    ISSUE3_LAST_ISOLATION_EVIDENCE.clear()
    ISSUE3_LAST_ISOLATION_EVIDENCE.update(
        {
            "tenant_database_name": db_name,
            "tenant_url_host": tenant_url.split("@")[-1].split("/")[0],
        }
    )
    return {"tenant_database_url": tenant_url, "tenant_db_name": db_name}


@pytest.fixture
async def issue3_http(client, override_auth_tenant, issue3_integration_gate):
    """Isolated HTTP context: tracks created load ids and deletes them in finally."""
    tenant_id = await platform_tenant_id_for_slug()
    await assert_mutating_integration_allowed(
        tenant_id=tenant_id,
        host=AUTH_HEADERS["host"],
        context="issue3_mark_ready_gate",
    )
    ISSUE3_LAST_ISOLATION_EVIDENCE["platform_tenant_id"] = tenant_id
    ISSUE3_LAST_ISOLATION_EVIDENCE["integration_host"] = AUTH_HEADERS["host"]

    gate = issue3_integration_gate
    created_load_ids: list[int] = []

    async def new_draft(tag: str, **extra) -> dict:
        r = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"{tag}-{uuid.uuid4().hex[:8]}", **extra},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        created_load_ids.append(int(body["id"]))
        return body

    ctx = SimpleNamespace(
        client=client,
        new_draft=new_draft,
        tenant_id=tenant_id,
        isolation_db_name=gate["tenant_db_name"],
        track_load=lambda lid: created_load_ids.append(int(lid)),
    )
    try:
        yield ctx
    finally:
        if not created_load_ids:
            return
        engine = create_async_engine(
            to_async_pg_url(gate["tenant_database_url"]), pool_pre_ping=True
        )
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                for load_id in reversed(created_load_ids):
                    await _cleanup_load_rows(db, tenant_id, load_id)
                for load_id in created_load_ids:
                    await _assert_load_absent(db, tenant_id, load_id)
        finally:
            await engine.dispose()
        ISSUE3_LAST_ISOLATION_EVIDENCE["cleaned_load_ids"] = ",".join(str(i) for i in created_load_ids)


@pytest.mark.skipif(SKIP_ISSUE3_HTTP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
class TestMarkReadyGateIssue3Http:
    async def test_patch_draft_to_ready_rejected_preserves_status_and_cv(self, issue3_http) -> None:
        assert issue3_http.isolation_db_name == integration_tenant_db_name()
        created = await issue3_http.new_draft(
            "I3-PATCH",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-1",
            stops=_VALID_STOPS,
        )
        cv_before = created["concurrency_version"]
        r = await issue3_http.client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={"status": "ready", "expected_concurrency_version": cv_before},
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT
        snap = (
            await issue3_http.client.get(f"/api/v1/loads/{created['id']}", headers=AUTH_HEADERS)
        ).json()
        assert snap["status"] == "draft"
        assert snap["concurrency_version"] == cv_before

    async def test_patch_ready_without_prerequisites_still_rejected(self, issue3_http) -> None:
        created = await issue3_http.new_draft("I3-NOPREQ")
        r = await issue3_http.client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={"status": "ready", "expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT

    async def test_commercial_patch_omitting_status_succeeds(self, issue3_http) -> None:
        created = await issue3_http.new_draft("I3-COMM")
        r = await issue3_http.client.patch(
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

    async def test_patch_explicit_ready_unchanged_on_ready_load(self, issue3_http) -> None:
        created = await issue3_http.new_draft(
            "I3-READY",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-2",
            stops=_VALID_STOPS,
        )
        mr = await issue3_http.client.post(
            f"/api/v1/loads/{created['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": created["concurrency_version"]},
        )
        assert mr.status_code == 200, mr.text
        ready = mr.json()
        r = await issue3_http.client.patch(
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

    async def test_mark_ready_success_with_prerequisites(self, issue3_http) -> None:
        created = await issue3_http.new_draft(
            "I3-MR-OK",
            broker_name_snapshot="Broker",
            broker_load_reference="REF-3",
            stops=_VALID_STOPS,
        )
        r = await issue3_http.client.post(
            f"/api/v1/loads/{created['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ready"

    async def test_mark_ready_rejects_missing_prerequisites(self, issue3_http) -> None:
        created = await issue3_http.new_draft("I3-MR-BAD")
        r = await issue3_http.client.post(
            f"/api/v1/loads/{created['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": created["concurrency_version"]},
        )
        assert r.status_code == 400

    async def test_post_legacy_status_still_rejected(self, issue3_http) -> None:
        ln = f"I3-LEG-{uuid.uuid4().hex[:8]}"
        r = await issue3_http.client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "dispatched", "load_number": ln},
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
