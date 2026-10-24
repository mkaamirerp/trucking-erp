"""Promoted load rate-confirmation PDF download + selectable text (Armstrong fixture)."""

from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.core.integration_db_guard import database_name_from_url
from app.core.storage import get_storage
from app.main import app
from app.schemas.load_workspace_draft import LoadWorkspaceDraftCreate, LoadWorkspaceDraftPromote
from app.services.load_workspace_draft import create_workspace_draft
from app.services.load_workspace_draft_document import LOAD_WORKSPACE_DRAFT_PDF_MODULE
from app.services.load_workspace_draft_promotion import promote_workspace_draft
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.integration_isolation import integration_auth_headers, integration_tenant_slug

REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
pytestmark = pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL not configured")

_ARMSTRONG_PDF = Path(__file__).resolve().parents[1] / "docs" / "_review" / "fixtures" / "pdf" / "Armstrong.pdf"
_ARMSTRONG_LOAD_REF = "3872125-1"

_PROMOTABLE_DRAFT_JSON = {
    "loadNumber": "",
    "brokerNameSnapshot": "Acme Brokerage",
    "brokerLoadReference": "PROMO-ARMSTRONG",
    "rate": "1200.00",
    "commodity": "General freight",
    "draftStops": [
        {"stopType": "PICKUP", "city": "Toronto", "stateOrProvince": "ON"},
        {"stopType": "DELIVERY", "city": "Montreal", "stateOrProvince": "QC"},
    ],
}


def _tenant_async_url() -> str:
    from app.core.db_url import to_async_pg_url

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    assert raw
    return to_async_pg_url(raw)


def _session():
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


async def _resolve_tenant_id(session: AsyncSession) -> int:
    tid = await session.scalar(text("SELECT MIN(tenant_id) FROM loads"))
    if tid is not None:
        return int(tid)
    tid = await session.scalar(text("SELECT MIN(tenant_id) FROM people"))
    if tid is None:
        pytest.skip("integration tenant has no loads/people rows")
    return int(tid)


def _pdf_extracted_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "".join((page.extract_text() or "") for page in reader.pages)


async def _delete_promoted_load_and_draft(factory, load_id: int | None, draft_id) -> None:
    async with factory() as db:
        if load_id is not None:
            await db.execute(text("DELETE FROM load_stops WHERE load_id = :id"), {"id": load_id})
            await db.execute(text("DELETE FROM load_commercial_evidence WHERE load_id = :id"), {"id": load_id})
            await db.execute(
                text("UPDATE loads SET promotion_origin_workspace_draft_id = NULL WHERE id = :id"),
                {"id": load_id},
            )
        if draft_id is not None:
            await db.execute(text("DELETE FROM load_workspace_drafts WHERE id = :id"), {"id": draft_id})
        if load_id is not None:
            await db.execute(text("DELETE FROM loads WHERE id = :id"), {"id": load_id})
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
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.mark.asyncio
async def test_load_rate_confirmation_pdf_armstrong_selectable_text(
    override_auth_tenant,
) -> None:
    """Stored Armstrong.pdf on a promoted load is downloadable with extractable text (copy/paste in UI)."""
    if database_name_from_url(_tenant_async_url()) == "tenant_demo":
        pytest.skip("mutation tests must not run on tenant_demo")
    if not _ARMSTRONG_PDF.is_file():
        pytest.skip("Armstrong.pdf fixture missing")

    pdf_bytes = _ARMSTRONG_PDF.read_bytes()
    engine, factory = _session()
    draft_id = None
    load_id = None
    tenant_slug = integration_tenant_slug()
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={
                        **_PROMOTABLE_DRAFT_JSON,
                        "loadNumber": f"ARM-{uuid.uuid4().hex[:8]}",
                    },
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id

        stored = await get_storage().save_bytes(
            tenant_slug,
            LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            "workspace_draft",
            str(draft_id),
            pdf_bytes,
            filename_hint="Armstrong.pdf",
            content_type="application/pdf",
        )

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            await db.execute(
                text(
                    """
                    UPDATE load_workspace_drafts
                    SET pdf_upload_state = 'ready',
                        pdf_storage_key = :key,
                        pdf_sha256 = :sha,
                        pdf_filename = 'Armstrong.pdf',
                        accepted_parse_json = '{"document":{"filename":"Armstrong.pdf"},"extracted":{"broker_load_reference":"3872125-1"},"raw_text":"","warnings":[]}'::jsonb,
                        accepted_parse_schema_version = 'load_document_parse_response_v1',
                        accepted_parse_pdf_sha256 = :sha
                    WHERE tenant_id = :tenant_id AND id = :id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "id": draft_id,
                    "key": stored.storage_key,
                    "sha": stored.sha256,
                },
            )
            await db.commit()

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=f"armstrong-pdf-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id

        headers = integration_auth_headers()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing = await client.get(f"/api/v1/loads/{load_id + 999999}/rate-confirmation-pdf", headers=headers)
            assert missing.status_code == 404

            res = await client.get(f"/api/v1/loads/{load_id}/rate-confirmation-pdf", headers=headers)
            assert res.status_code == 200
            assert res.headers.get("content-type", "").startswith("application/pdf")
            body = res.content
            assert body[:4] == b"%PDF"

        extracted = _pdf_extracted_text(body)
        assert _ARMSTRONG_LOAD_REF in extracted
        assert "Armstrong" in extracted
    finally:
        await _delete_promoted_load_and_draft(factory, load_id, draft_id)
        await engine.dispose()
