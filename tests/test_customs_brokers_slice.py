"""Customs broker vertical slice: tenant isolation, load link, confirm snapshot, PATCH freeze."""
from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_TENANT_RESOLUTION_SHORTCUTS"] = "true"
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_mutable_tenant_current_user_and_tenant,
)

REQUIRES_DB = not os.environ.get("DATABASE_URL")
AUTH_HEADERS = {"host": "demo.truckerp.me"}


@pytest.fixture(autouse=True)
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
def tenant_resolver():
    """Mutable tenant id for dependency injection (isolation tests use platform ids 1 vs 2)."""
    holder = {"tenant_id": 1}
    install_mutable_tenant_current_user_and_tenant(
        app, holder, role="TENANT_ADMIN", user_id="test-user-customs", email="test@example.com"
    )
    yield holder
    clear_current_user_and_tenant_overrides(app)


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestCustomsBrokersTenantIsolation:
    async def test_cross_tenant_cannot_fetch_broker(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        c = await client.post(
            "/api/v1/customs-brokers",
            json={"legal_name": f"Broker A {uuid.uuid4().hex[:6]}", "is_active": True},
            headers=AUTH_HEADERS,
        )
        assert c.status_code == 201
        broker_id = c.json()["id"]

        tenant_resolver["tenant_id"] = 2
        g = await client.get(f"/api/v1/customs-brokers/{broker_id}", headers=AUTH_HEADERS)
        assert g.status_code == 404

    async def test_search_only_same_tenant(self, client, tenant_resolver) -> None:
        suffix = uuid.uuid4().hex[:8]
        tenant_resolver["tenant_id"] = 1
        await client.post(
            "/api/v1/customs-brokers",
            json={"legal_name": f"UniqueSearchAlpha {suffix}", "phone_primary": "+15550001111", "is_active": True},
            headers=AUTH_HEADERS,
        )
        tenant_resolver["tenant_id"] = 2
        await client.post(
            "/api/v1/customs-brokers",
            json={"legal_name": f"UniqueSearchBeta {suffix}", "phone_primary": "+15550002222", "is_active": True},
            headers=AUTH_HEADERS,
        )

        tenant_resolver["tenant_id"] = 1
        r = await client.get(f"/api/v1/customs-brokers/search?q={suffix}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        names = [x["legal_name"] for x in r.json().get("items", [])]
        assert any(f"UniqueSearchAlpha {suffix}" in n for n in names)
        assert not any("UniqueSearchBeta" in n for n in names)


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestLoadCustomsConfirmAndFreeze:
    async def test_patch_confirm_get_second_confirm_rejected(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        cb = await client.post(
            "/api/v1/customs-brokers",
            json={"legal_name": f"CB {uuid.uuid4().hex[:6]}", "fax": "+15559998877", "is_active": True},
            headers=AUTH_HEADERS,
        )
        assert cb.status_code == 201
        customs_broker_id = cb.json()["id"]

        ln = f"L-CUST-{uuid.uuid4().hex[:8]}"
        cr = await client.post(
            "/api/v1/loads",
            json={"status": "draft", "load_number": ln},
            headers=AUTH_HEADERS,
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        cv0 = cr.json()["concurrency_version"]

        patch = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"customs_broker_id": customs_broker_id, "expected_concurrency_version": cv0},
            headers=AUTH_HEADERS,
        )
        assert patch.status_code == 200
        assert patch.json()["customs_broker_id"] == customs_broker_id
        assert patch.json().get("document_snapshot_confirmed_at") is None
        cv1 = patch.json()["concurrency_version"]

        bad = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"customs_broker_id": customs_broker_id + 99999, "expected_concurrency_version": cv1},
            headers=AUTH_HEADERS,
        )
        assert bad.status_code == 400

        conf = await client.post(
            f"/api/v1/loads/{load_id}/confirm-document-snapshot",
            json={"expected_concurrency_version": cv1},
            headers=AUTH_HEADERS,
        )
        assert conf.status_code == 200
        body = conf.json()
        assert body.get("document_snapshot_confirmed_at") is not None
        assert body.get("document_snapshot_version", 0) >= 1
        snap = body.get("customs_snapshot") or {}
        assert snap.get("legal_name_snapshot") == cb.json()["legal_name"]
        assert snap.get("fax_snapshot") == "+15559998877"
        assert snap.get("customs_broker_id_at_confirm") == customs_broker_id

        cv_after_confirm = conf.json()["concurrency_version"]
        again = await client.post(
            f"/api/v1/loads/{load_id}/confirm-document-snapshot",
            json={"expected_concurrency_version": cv_after_confirm},
            headers=AUTH_HEADERS,
        )
        assert again.status_code == 409
        assert again.json().get("detail", {}).get("code") == "DOCUMENT_SNAPSHOT_ALREADY_CONFIRMED"

        gl = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        assert gl.status_code == 200
        cv_gl = gl.json()["concurrency_version"]

        blocked = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"customs_broker_id": None, "expected_concurrency_version": cv_gl},
            headers=AUTH_HEADERS,
        )
        assert blocked.status_code == 400

        gl2 = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        assert gl2.status_code == 200
        assert gl2.json()["customs_snapshot"] is not None

    async def test_cannot_assign_other_tenant_customs_broker_to_load(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        cb = await client.post(
            "/api/v1/customs-brokers",
            json={"legal_name": f"Tenant1 CB {uuid.uuid4().hex[:6]}", "is_active": True},
            headers=AUTH_HEADERS,
        )
        customs_broker_id = cb.json()["id"]

        tenant_resolver["tenant_id"] = 2
        ln = f"L-CTX-{uuid.uuid4().hex[:8]}"
        cr = await client.post("/api/v1/loads", json={"status": "draft", "load_number": ln}, headers=AUTH_HEADERS)
        load_id = cr.json()["id"]
        cv0 = cr.json()["concurrency_version"]

        patch = await client.patch(
            f"/api/v1/loads/{load_id}",
            json={"customs_broker_id": customs_broker_id, "expected_concurrency_version": cv0},
            headers=AUTH_HEADERS,
        )
        assert patch.status_code == 400


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
async def test_migration_customs_tables_exist():
    """information_schema check using asyncpg tenant URL (same driver/creds as API tests)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    tenant_url = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not tenant_url:
        pytest.skip("tenant database URL not in environment")
    if "+asyncpg" not in tenant_url:
        pytest.skip("use postgresql+asyncpg tenant URL for this smoke test")

    eng = create_async_engine(tenant_url)
    try:
        try:
            async with eng.connect() as conn:
                for tbl in ("customs_brokers", "customs_broker_contacts", "load_customs_snapshots"):
                    r = await conn.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                            "WHERE table_schema='public' AND table_name=:t)"
                        ),
                        {"t": tbl},
                    )
                    assert r.scalar() is True, f"missing table {tbl}"
                r2 = await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name='loads' "
                        "AND column_name IN ('customs_broker_id','document_snapshot_confirmed_at','document_snapshot_version')"
                    )
                )
                assert r2.scalar() == 3
        except Exception as e:
            if "password authentication" in str(e).lower() or "invalidpassword" in type(e).__name__.lower():
                pytest.skip(f"tenant DB migration smoke skipped (credentials): {e}")
            raise
    finally:
        await eng.dispose()
