"""Load integrity — Claude correction pass 1 (response status, ready invariants, PDF read bound)."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.constants.trip_dispatch import LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT
from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError, integration_tenant_db_name
from app.main import app
from app.routers.loads import _MAX_PARSE_PDF_BYTES
from app.schemas.load_document_parse import LoadDocumentParseResponse, LoadParseDocumentMeta, LoadParseExtractedFields
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


def _detail_code(payload: dict) -> str | None:
    d = payload.get("detail")
    return d.get("code") if isinstance(d, dict) else None


def _integration_db_configured() -> bool:
    try:
        require_integration_tenant_database_url(context="correction_pass1")
        return True
    except IntegrationIsolationError:
        return False


_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
SKIP_HTTP = _PLACEHOLDER_PLATFORM_DB or not _integration_db_configured()


async def _cleanup_load_rows(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context="cp1_cleanup_load")
    await db.execute(
        text("delete from audit_events where tenant_id=:t and entity_type='load' and entity_id=:e"),
        {"t": tenant_id, "e": str(load_id)},
    )
    await db.execute(text("delete from load_stops where tenant_id=:t and load_id=:i"), {"t": tenant_id, "i": load_id})
    await db.execute(text("delete from load_notes where tenant_id=:t and load_id=:i"), {"t": tenant_id, "i": load_id})
    await db.execute(text("delete from loads where tenant_id=:t and id=:i"), {"t": tenant_id, "i": load_id})
    await db.commit()


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
def cp1_integration_gate():
    try:
        tenant_url = require_integration_tenant_database_url(context="correction_pass1")
    except IntegrationIsolationError as exc:
        pytest.skip(f"Correction pass 1 HTTP tests require isolated tenant DB: {exc}")
    db_name = database_name_from_url(tenant_url)
    expected = integration_tenant_db_name()
    if db_name != expected:
        pytest.skip(f"Requires database {expected!r}, got {db_name!r}")
    return {"tenant_database_url": tenant_url, "tenant_db_name": db_name}


@pytest.fixture
async def cp1_http(client, override_auth_tenant, cp1_integration_gate):
    tenant_id = await platform_tenant_id_for_slug()
    await assert_mutating_integration_allowed(
        tenant_id=tenant_id,
        host=AUTH_HEADERS["host"],
        context="correction_pass1",
    )
    gate = cp1_integration_gate
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

    async def mark_ready(load: dict) -> dict:
        r = await client.post(
            f"/api/v1/loads/{load['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": load["concurrency_version"]},
        )
        assert r.status_code == 200, r.text
        return r.json()

    ctx = SimpleNamespace(
        client=client,
        new_draft=new_draft,
        mark_ready=mark_ready,
        tenant_id=tenant_id,
        tenant_url=gate["tenant_database_url"],
    )
    try:
        yield ctx
    finally:
        if created_load_ids:
            engine = create_async_engine(to_async_pg_url(gate["tenant_database_url"]), pool_pre_ping=True)
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            try:
                async with Session() as db:
                    for load_id in reversed(created_load_ids):
                        await _cleanup_load_rows(db, tenant_id, load_id)
            finally:
                await engine.dispose()


async def _set_load_status_raw(tenant_url: str, tenant_id: int, load_id: int, status: str | None) -> None:
    engine = create_async_engine(to_async_pg_url(tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        if status is None:
            await db.execute(
                text("update loads set status=null where tenant_id=:t and id=:i"),
                {"t": tenant_id, "i": load_id},
            )
        else:
            await db.execute(
                text("update loads set status=:s where tenant_id=:t and id=:i"),
                {"s": status, "t": tenant_id, "i": load_id},
            )
        await db.commit()
    await engine.dispose()


async def _fetch_load_row(tenant_url: str, tenant_id: int, load_id: int) -> dict:
    engine = create_async_engine(to_async_pg_url(tenant_url), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        row = (
            await db.execute(
                text(
                    "select broker_load_reference, status from loads where tenant_id=:t and id=:i"
                ),
                {"t": tenant_id, "i": load_id},
            )
        ).one()
        stop_count = await db.scalar(
            text("select count(*) from load_stops where tenant_id=:t and load_id=:i"),
            {"t": tenant_id, "i": load_id},
        )
    await engine.dispose()
    return {"broker_load_reference": row[0], "status": row[1], "stop_count": int(stop_count or 0)}


@pytest.mark.skipif(SKIP_HTTP, reason="isolated integration tenant DB required (tenant_pytest)")
@pytest.mark.asyncio
class TestLoadIntegrityCorrectionPass1Http:
    async def test_cancelled_load_get_and_list(self, cp1_http) -> None:
        draft = await cp1_http.new_draft(
            "CP1-CANCEL",
            broker_name_snapshot="B",
            broker_load_reference="REF-C",
            stops=_VALID_STOPS,
        )
        ready = await cp1_http.mark_ready(draft)
        cancel = await cp1_http.client.post(
            f"/api/v1/loads/{ready['id']}/cancel",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": ready["concurrency_version"], "reason": "test"},
        )
        assert cancel.status_code == 200, cancel.text
        cancelled = cancel.json()
        assert cancelled["status"] == "cancelled"

        got = await cp1_http.client.get(f"/api/v1/loads/{cancelled['id']}", headers=AUTH_HEADERS)
        assert got.status_code == 200
        assert got.json()["status"] == "cancelled"

        listed = await cp1_http.client.get("/api/v1/loads", headers=AUTH_HEADERS)
        assert listed.status_code == 200
        ids = {item["id"] for item in listed.json().get("items", [])}
        assert cancelled["id"] in ids

    async def test_unknown_legacy_status_list_and_get_do_not_coerce_ready(self, cp1_http) -> None:
        draft = await cp1_http.new_draft("CP1-UNK", broker_name_snapshot="B", broker_load_reference="R1")
        load_id = draft["id"]
        await _set_load_status_raw(cp1_http.tenant_url, cp1_http.tenant_id, load_id, "legacy_ops_foo")

        got = await cp1_http.client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        assert got.status_code == 200
        assert got.json()["status"] == "legacy_ops_foo"
        assert got.json()["status"] != "ready"

        listed = await cp1_http.client.get("/api/v1/loads", headers=AUTH_HEADERS)
        assert listed.status_code == 200
        match = next((x for x in listed.json().get("items", []) if x["id"] == load_id), None)
        assert match is not None
        assert match["status"] == "legacy_ops_foo"

    async def test_invalid_write_status_still_rejected(self, cp1_http) -> None:
        draft = await cp1_http.new_draft("CP1-BAD-STATUS")
        r = await cp1_http.client.patch(
            f"/api/v1/loads/{draft['id']}",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": draft["concurrency_version"], "status": "not_a_real_status"},
        )
        assert r.status_code == 422

    async def test_ready_clear_broker_reference_rejected_db_unchanged(self, cp1_http) -> None:
        ready = await cp1_http.mark_ready(
            await cp1_http.new_draft(
                "CP1-RDY-REF",
                broker_name_snapshot="B",
                broker_load_reference="KEEP-ME",
                stops=_VALID_STOPS,
            )
        )
        load_id = ready["id"]
        ref_before = (await _fetch_load_row(cp1_http.tenant_url, cp1_http.tenant_id, load_id))[
            "broker_load_reference"
        ]

        r = await cp1_http.client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": ready["concurrency_version"],
                "broker_load_reference": "",
            },
        )
        assert r.status_code == 409, r.text
        assert _detail_code(r.json()) == "LOAD_READY_REQUIREMENTS_VIOLATED"

        after = await _fetch_load_row(cp1_http.tenant_url, cp1_http.tenant_id, load_id)
        assert after["broker_load_reference"] == ref_before
        assert after["status"] == "ready"

    async def test_ready_remove_all_stops_rejected(self, cp1_http) -> None:
        ready = await cp1_http.mark_ready(
            await cp1_http.new_draft(
                "CP1-RDY-STOPS",
                broker_name_snapshot="B",
                broker_load_reference="REF",
                stops=_VALID_STOPS,
            )
        )
        stops_before = (await _fetch_load_row(cp1_http.tenant_url, cp1_http.tenant_id, ready["id"]))["stop_count"]
        r = await cp1_http.client.patch(
            f"/api/v1/loads/{ready['id']}",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": ready["concurrency_version"], "stops": []},
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == "LOAD_READY_REQUIREMENTS_VIOLATED"
        assert (
            await _fetch_load_row(cp1_http.tenant_url, cp1_http.tenant_id, ready["id"])
        )["stop_count"] == stops_before

    async def test_ready_remove_last_pickup_rejected(self, cp1_http) -> None:
        ready = await cp1_http.mark_ready(
            await cp1_http.new_draft(
                "CP1-RDY-PU",
                broker_name_snapshot="B",
                broker_load_reference="REF",
                stops=_VALID_STOPS,
            )
        )
        drop_only = [s for s in ready["stops"] if s["stop_type"].upper() in ("DROP", "DELIVERY")]
        r = await cp1_http.client.patch(
            f"/api/v1/loads/{ready['id']}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": ready["concurrency_version"],
                "stops": drop_only,
            },
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == "LOAD_READY_REQUIREMENTS_VIOLATED"

    async def test_ready_remove_last_delivery_rejected(self, cp1_http) -> None:
        ready = await cp1_http.mark_ready(
            await cp1_http.new_draft(
                "CP1-RDY-DLV",
                broker_name_snapshot="B",
                broker_load_reference="REF",
                stops=_VALID_STOPS,
            )
        )
        pickup_only = [s for s in ready["stops"] if s["stop_type"].upper() == "PICKUP"]
        r = await cp1_http.client.patch(
            f"/api/v1/loads/{ready['id']}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": ready["concurrency_version"],
                "stops": pickup_only,
            },
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == "LOAD_READY_REQUIREMENTS_VIOLATED"

    async def test_valid_ready_commercial_edit_accepted(self, cp1_http) -> None:
        ready = await cp1_http.mark_ready(
            await cp1_http.new_draft(
                "CP1-RDY-OK",
                broker_name_snapshot="B",
                broker_load_reference="REF",
                stops=_VALID_STOPS,
            )
        )
        r = await cp1_http.client.patch(
            f"/api/v1/loads/{ready['id']}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": ready["concurrency_version"],
                "commodity": "Widgets",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["commodity"] == "Widgets"
        assert r.json()["status"] == "ready"

    async def test_draft_incomplete_still_editable(self, cp1_http) -> None:
        draft = await cp1_http.new_draft("CP1-DRAFT", stops=_VALID_STOPS)
        r = await cp1_http.client.patch(
            f"/api/v1/loads/{draft['id']}",
            headers=AUTH_HEADERS,
            json={
                "expected_concurrency_version": draft["concurrency_version"],
                "broker_name_snapshot": "Late Broker",
            },
        )
        assert r.status_code == 200, r.text

    async def test_mark_ready_still_validates_requirements(self, cp1_http) -> None:
        draft = await cp1_http.new_draft("CP1-MR", stops=_VALID_STOPS)
        r = await cp1_http.client.post(
            f"/api/v1/loads/{draft['id']}/mark-ready",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": draft["concurrency_version"]},
        )
        assert r.status_code == 400

    async def test_patch_draft_to_ready_still_blocked(self, cp1_http) -> None:
        draft = await cp1_http.new_draft(
            "CP1-I3",
            broker_name_snapshot="B",
            broker_load_reference="REF",
            stops=_VALID_STOPS,
        )
        r = await cp1_http.client.patch(
            f"/api/v1/loads/{draft['id']}",
            headers=AUTH_HEADERS,
            json={"expected_concurrency_version": draft["concurrency_version"], "status": "ready"},
        )
        assert r.status_code == 409
        assert _detail_code(r.json()) == LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT


@pytest.mark.asyncio
class TestLoadIntegrityCorrectionPass1Pdf:
    async def test_empty_upload_rejected(self, client, override_auth_tenant) -> None:
        r = await client.post(
            "/api/v1/loads/parse-document",
            headers=AUTH_HEADERS,
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert r.status_code == 400

    async def test_oversized_upload_413_never_calls_orchestrator(self, client, override_auth_tenant) -> None:
        payload = b"%PDF-" + (b"0" * (_MAX_PARSE_PDF_BYTES + 1))
        with patch(
            "app.routers.loads.parse_load_workspace_document_orchestrated",
            new_callable=AsyncMock,
        ) as mock_orch:
            r = await client.post(
                "/api/v1/loads/parse-document",
                headers=AUTH_HEADERS,
                files={"file": ("big.pdf", payload, "application/pdf")},
            )
        assert r.status_code == 413
        mock_orch.assert_not_called()

    async def test_valid_pdf_reaches_orchestrator(self, client, override_auth_tenant) -> None:
        small = b"%PDF-1.4 minimal\n%%EOF"
        stub = LoadDocumentParseResponse(
            document=LoadParseDocumentMeta(filename="ok.pdf", content_type="application/pdf"),
            extracted=LoadParseExtractedFields(),
            raw_text="",
        )
        with patch(
            "app.routers.loads.parse_load_workspace_document_orchestrated",
            new_callable=AsyncMock,
            return_value=stub,
        ) as mock_orch:
            r = await client.post(
                "/api/v1/loads/parse-document",
                headers=AUTH_HEADERS,
                files={"file": ("ok.pdf", small, "application/pdf")},
            )
        assert r.status_code == 200
        mock_orch.assert_awaited_once()


def test_load_response_accepts_unknown_status_from_attributes() -> None:
    from app.schemas.load import LoadResponse

    model = LoadResponse.model_validate(
        {
            "id": 1,
            "load_number": "L-1",
            "status": "legacy_unknown_bucket",
            "concurrency_version": 1,
            "operational_references": [],
        }
    )
    assert model.status == "legacy_unknown_bucket"
