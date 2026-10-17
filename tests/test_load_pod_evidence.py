"""Proof of Delivery evidence on Loads — no custody, Trip, or commercial document changes."""

from __future__ import annotations

import io
import os
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.core.storage import StoredFile
from app.main import app
from app.models.tenant import AuditEvent
from app.services.load_pod_evidence import classify_pod_bytes
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.demo_clone_integration import (
    demo_clone_active,
    demo_clone_tenant_id,
    install_demo_clone_tenant_db_override,
)
from tests.support.integration_test_resources import integration_scope_context

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "pytest.truckerp.me"}
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
# Placeholder platform URL is allowed when a real tenant DB is configured (demo clone E2E).
_SKIP_WITHOUT_TENANT = _PLACEHOLDER_PLATFORM_DB and REQUIRES_TENANT_DB

pytestmark = [
    pytest.mark.skipif(REQUIRES_DB or _SKIP_WITHOUT_TENANT, reason="DATABASE_URL not configured"),
    pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL not configured"),
]


def _tenant_async_url() -> str:
    from app.core.db_url import to_async_pg_url

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    assert raw
    return to_async_pg_url(raw)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


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
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    install_demo_clone_tenant_db_override(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def integration_scope(client, override_auth_tenant):
    async with integration_scope_context(client, AUTH_HEADERS, "pod_evidence") as scope:
        yield scope


async def _scalar(sql: str, params: dict):
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            result = await session.execute(text(sql), params)
            return result.scalar()
    finally:
        await engine.dispose()


async def _upload(client: AsyncClient, load_id: int, body: bytes, filename: str, content_type: str):
    return await client.post(
        f"/api/v1/loads/{load_id}/pod",
        headers=AUTH_HEADERS,
        files={"file": (filename, io.BytesIO(body), content_type)},
    )


class TestPodFileValidation:
    def test_classify_pdf_jpeg_png(self):
        assert classify_pod_bytes(b"%PDF-1.4\n") == ("application/pdf", ".pdf")
        assert classify_pod_bytes(b"\xff\xd8\xff\xe0") == ("image/jpeg", ".jpg")
        assert classify_pod_bytes(b"\x89PNG\r\n\x1a\n") == ("image/png", ".png")

    def test_rejects_text_payload(self):
        with pytest.raises(Exception) as exc:
            classify_pod_bytes(b"not-a-pod")
        assert getattr(exc.value, "code", None) == "INVALID_POD_FILE_TYPE"

    def test_demo_clone_data_and_pod_schema(self) -> None:
        if not demo_clone_active():
            pytest.skip("demo clone E2E only")

        async def _check() -> None:
            pod_table = await _scalar(
                "select count(*) from information_schema.tables "
                "where table_schema = 'public' and table_name = 'load_pod_evidence'",
                {},
            )
            assert int(pod_table or 0) == 1
            loads = await _scalar(
                "select count(*) from loads where tenant_id = :t",
                {"t": demo_clone_tenant_id()},
            )
            assert int(loads or 0) >= 200
            links = await _scalar("select count(*) from trip_loads", {})
            assert int(links or 0) > 0

        import asyncio

        asyncio.run(_check())


@contextmanager
def _fail_pod_audit_flush():
    real_flush = AsyncSession.flush

    async def flush_wrapper(self, *args, **kwargs):
        for obj in list(self.new):
            if isinstance(obj, AuditEvent) and obj.action == "pod_evidence_uploaded":
                raise RuntimeError("pod audit flush failure")
        return await real_flush(self, *args, **kwargs)

    with patch.object(AsyncSession, "flush", flush_wrapper):
        yield


class TestLoadPodEvidenceApi:
    async def test_upload_list_download_and_second_attachment(
        self, client: AsyncClient, integration_scope
    ):
        load_id = (await integration_scope.create_ready_load_ids(1, tag_prefix="POD"))[0]
        before_status = (
            await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        ).json()["status"]
        commercial_before = await _scalar("select count(*) from load_commercial_evidence where load_id = :lid", {"lid": load_id})

        pdf = b"%PDF-1.4 pod one"
        up1 = await _upload(client, load_id, pdf, "receiver-one.pdf", "application/pdf")
        assert up1.status_code == 201, up1.text
        pod1 = up1.json()
        assert pod1["original_filename"]
        assert pod1["file_sha256"]

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
        up2 = await _upload(client, load_id, png, "receiver-two.png", "image/png")
        assert up2.status_code == 201

        listed = await client.get(f"/api/v1/loads/{load_id}/pod", headers=AUTH_HEADERS)
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert len(items) == 2
        assert items[0]["id"] != items[1]["id"]

        dl = await client.get(
            f"/api/v1/loads/{load_id}/pod/{pod1['id']}/file",
            headers=AUTH_HEADERS,
        )
        assert dl.status_code == 200
        assert dl.content == pdf

        after = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        assert after.json()["status"] == before_status
        commercial_after = await _scalar(
            "select count(*) from load_commercial_evidence where load_id = :lid",
            {"lid": load_id},
        )
        assert commercial_after == commercial_before

        audits = await _scalar(
            "select count(*) from audit_events where module = 'loads' and action = 'pod_evidence_uploaded' and entity_id = :eid",
            {"eid": str(load_id)},
        )
        assert audits == 2

    async def test_rejects_invalid_type_and_empty(self, client: AsyncClient, integration_scope):
        load_id = (await integration_scope.create_ready_load_ids(1, tag_prefix="POD-BAD"))[0]
        bad = await _upload(client, load_id, b"hello", "notes.txt", "text/plain")
        assert bad.status_code == 400
        assert bad.json()["detail"]["code"] == "INVALID_POD_FILE_TYPE"

        empty = await client.post(
            f"/api/v1/loads/{load_id}/pod",
            headers=AUTH_HEADERS,
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert empty.status_code == 400

        count = await _scalar("select count(*) from load_pod_evidence where load_id = :lid", {"lid": load_id})
        assert count == 0

    async def test_download_not_found_for_wrong_load(self, client: AsyncClient, integration_scope):
        load_a, load_b = await integration_scope.create_ready_load_ids(2, tag_prefix="POD-ISO")
        up = await _upload(client, load_a, b"%PDF-1.4 x", "a.pdf", "application/pdf")
        pod_id = up.json()["id"]
        cross = await client.get(
            f"/api/v1/loads/{load_b}/pod/{pod_id}/file",
            headers=AUTH_HEADERS,
        )
        assert cross.status_code == 404

    async def test_audit_failure_rolls_back_row_and_deletes_storage(
        self, client: AsyncClient, integration_scope
    ):
        load_id = (await integration_scope.create_ready_load_ids(1, tag_prefix="POD-AUDIT"))[0]
        stored_key = f"pytest/load_pod/load/{load_id}/{uuid.uuid4().hex}.pdf"
        mock_backend = MagicMock()
        mock_backend.save_bytes = AsyncMock(
            return_value=StoredFile(
                storage_key=stored_key,
                original_filename="signed.pdf",
                content_type="application/pdf",
                file_size_bytes=9,
                sha256="deadbeef",
            )
        )
        mock_backend.delete = MagicMock()

        with patch("app.services.load_pod_evidence.get_storage", return_value=mock_backend):
            with _fail_pod_audit_flush():
                with pytest.raises(RuntimeError, match="pod audit flush failure"):
                    await _upload(client, load_id, b"%PDF-1.4", "signed.pdf", "application/pdf")

        mock_backend.delete.assert_called_once()
        count = await _scalar("select count(*) from load_pod_evidence where load_id = :lid", {"lid": load_id})
        assert count == 0
        audit_count = await _scalar(
            "select count(*) from audit_events where action = 'pod_evidence_uploaded' and entity_id = :eid",
            {"eid": str(load_id)},
        )
        assert audit_count == 0
