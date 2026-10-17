"""Load workspace draft application layer (service + optional HTTP on demo clone)."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.main import app
from app.schemas.load_workspace_draft import (
    LoadWorkspaceDraftCreate,
    LoadWorkspaceDraftPromote,
    LoadWorkspaceDraftUpdate,
)
from app.services.load_workspace_draft import (
    create_workspace_draft,
    get_workspace_draft,
    update_workspace_draft,
)
from app.services.load_workspace_draft_mapper import DraftJsonMappingError, draft_json_to_load_create
from app.services.load_workspace_draft_lifecycle import discard_workspace_draft
from app.services.load_workspace_draft_promotion import promote_workspace_draft
from fastapi import HTTPException
from tests.support.demo_clone_integration import demo_clone_active, install_demo_clone_tenant_db_override
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)

REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "pytest.truckerp.me"}

SAMPLE_DRAFT_JSON = {
    "loadNumber": "DW1-API-TEST",
    "brokerNameSnapshot": "Acme Brokerage",
    "rate": "1200.00",
    "commodity": "General freight",
    "draftStops": [],
}

pytestmark = pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL not configured")


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


@pytest.mark.asyncio
async def test_service_create_get_update_without_creating_load() -> None:
    engine, factory = _session()
    created_id: uuid.UUID | None = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            loads_before = await db.scalar(text("SELECT COUNT(*) FROM loads"))

            row = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(source_channel="manual", draft_json=SAMPLE_DRAFT_JSON),
                created_by_platform_user_id="integration-test-user",
            )
            created_id = row.id
            assert row.status == "draft"
            assert row.concurrency_version == 1
            assert row.draft_json["loadNumber"] == SAMPLE_DRAFT_JSON["loadNumber"]

            loads_after_create = await db.scalar(text("SELECT COUNT(*) FROM loads"))
            assert loads_after_create == loads_before

            fetched = await get_workspace_draft(db, tenant_id, row.id)
            assert fetched is not None
            assert fetched.id == row.id

            updated_json = {**SAMPLE_DRAFT_JSON, "rate": "1500.00"}
            updated = await update_workspace_draft(
                db,
                tenant_id,
                row.id,
                LoadWorkspaceDraftUpdate(expected_concurrency_version=1, draft_json=updated_json),
                updated_by_platform_user_id="integration-test-user",
            )
            assert updated.concurrency_version == 2
            assert updated.draft_json["rate"] == "1500.00"

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                await update_workspace_draft(
                    db,
                    tenant_id,
                    row.id,
                    LoadWorkspaceDraftUpdate(expected_concurrency_version=1, draft_json=updated_json),
                    updated_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "LOAD_WORKSPACE_DRAFT_VERSION_CONFLICT"

            loads_after_update = await db.scalar(text("SELECT COUNT(*) FROM loads"))
            assert loads_after_update == loads_before
    finally:
        if created_id is not None:
            async with factory() as db:
                await db.execute(
                    text("DELETE FROM load_workspace_drafts WHERE id = :id"),
                    {"id": created_id},
                )
                await db.commit()
        await engine.dispose()


@pytest.mark.skipif(not demo_clone_active(), reason="HTTP draft API requires demo clone runner env")
@pytest.mark.asyncio
async def test_http_create_get_update_on_demo_clone() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        old_bypass = os.environ.get("TEST_BYPASS_AUTH")
        os.environ["TEST_BYPASS_AUTH"] = "1"
        install_host_aligned_current_user_and_tenant(app)
        install_demo_clone_tenant_db_override(app)
        created_ids: list[str] = []
        try:
            loads_before = await _scalar_count("SELECT COUNT(*) FROM loads")
            create_resp = await client.post(
                "/api/v1/load-workspace-drafts",
                headers=AUTH_HEADERS,
                json={"source_channel": "manual", "draft_json": SAMPLE_DRAFT_JSON},
            )
            assert create_resp.status_code == 201, create_resp.text
            draft_id = create_resp.json()["id"]
            created_ids.append(draft_id)

            assert await _scalar_count("SELECT COUNT(*) FROM loads") == loads_before

            get_resp = await client.get(
                f"/api/v1/load-workspace-drafts/{draft_id}",
                headers=AUTH_HEADERS,
            )
            assert get_resp.status_code == 200

            patch_resp = await client.patch(
                f"/api/v1/load-workspace-drafts/{draft_id}",
                headers=AUTH_HEADERS,
                json={
                    "expected_concurrency_version": 1,
                    "draft_json": {**SAMPLE_DRAFT_JSON, "rate": "999.00"},
                },
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["concurrency_version"] == 2
        finally:
            for draft_id in created_ids:
                engine, factory = _session()
                try:
                    async with factory() as db:
                        await db.execute(
                            text("DELETE FROM load_workspace_drafts WHERE id = :id"),
                            {"id": draft_id},
                        )
                        await db.commit()
                finally:
                    await engine.dispose()
            clear_current_user_and_tenant_overrides(app)
            if old_bypass is None:
                os.environ.pop("TEST_BYPASS_AUTH", None)
            else:
                os.environ["TEST_BYPASS_AUTH"] = old_bypass


def test_mapper_rejects_invalid_rate() -> None:
    with pytest.raises(DraftJsonMappingError) as exc:
        draft_json_to_load_create({"rate": "not-a-number"})
    assert exc.value.field == "rate"


def test_mapper_rejects_invalid_reference_entry() -> None:
    with pytest.raises(DraftJsonMappingError) as exc:
        draft_json_to_load_create({"loadReferences": [{"kind": "po"}]})
    assert exc.value.field.startswith("loadReferences")


@pytest.mark.asyncio
async def test_service_promote_creates_one_load_with_origin_link() -> None:
    engine, factory = _session()
    draft_id = None
    load_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            loads_before = await db.scalar(text("SELECT COUNT(*) FROM loads"))

            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={**SAMPLE_DRAFT_JSON, "loadNumber": f"PROMO-{uuid.uuid4().hex[:8]}"},
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            promo_key = f"promo-{uuid.uuid4().hex}"
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=promo_key,
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id
            assert result.idempotent_replay is False

            replay = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=promo_key,
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            assert replay.idempotent_replay is True
            assert replay.load_id == load_id

        async with factory() as db:
            loads_after = await db.scalar(text("SELECT COUNT(*) FROM loads"))
            assert loads_after == loads_before + 1
            origin = await db.scalar(
                text(
                    "SELECT promotion_origin_workspace_draft_id FROM loads WHERE id = :id"
                ),
                {"id": load_id},
            )
            assert str(origin) == str(draft_id)
    finally:
        if load_id is not None or draft_id is not None:
            async with factory() as db:
                if load_id is not None:
                    await db.execute(text("DELETE FROM load_stops WHERE load_id = :id"), {"id": load_id})
                    await db.execute(
                        text("DELETE FROM load_commercial_evidence WHERE load_id = :id"),
                        {"id": load_id},
                    )
                    await db.execute(
                        text(
                            "UPDATE loads SET promotion_origin_workspace_draft_id = NULL WHERE id = :id"
                        ),
                        {"id": load_id},
                    )
                if draft_id is not None:
                    await db.execute(
                        text("DELETE FROM load_workspace_drafts WHERE id = :id"),
                        {"id": draft_id},
                    )
                if load_id is not None:
                    await db.execute(text("DELETE FROM loads WHERE id = :id"), {"id": load_id})
                await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_service_discard_unpromoted_draft() -> None:
    engine, factory = _session()
    draft_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            row = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={**SAMPLE_DRAFT_JSON, "loadNumber": f"DISC-{uuid.uuid4().hex[:8]}"},
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = row.id

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            discarded = await discard_workspace_draft(
                db,
                tenant_id,
                "pytest",
                draft_id,
                discard_reason="integration discard",
                updated_by_platform_user_id="integration-test-user",
            )
            assert discarded.status == "discarded"
            assert discarded.discarded_at is not None
            assert discarded.discard_reason == "integration discard"
            assert discarded.pdf_upload_state == "idle"
    finally:
        if draft_id is not None:
            async with factory() as db:
                await db.execute(
                    text("DELETE FROM load_workspace_drafts WHERE id = :id"),
                    {"id": draft_id},
                )
                await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_expired_draft_cannot_be_promoted() -> None:
    engine, factory = _session()
    draft_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            row = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={**SAMPLE_DRAFT_JSON, "loadNumber": f"EXP-{uuid.uuid4().hex[:8]}"},
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = row.id
            await db.execute(
                text(
                    """
                    UPDATE load_workspace_drafts
                    SET expires_at = now() - interval '1 hour'
                    WHERE tenant_id = :tenant_id AND id = :id
                    """
                ),
                {"tenant_id": tenant_id, "id": draft_id},
            )
            await db.commit()

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            with pytest.raises(HTTPException) as exc:
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"exp-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "LOAD_WORKSPACE_DRAFT_NOT_EDITABLE"
            assert exc.value.detail["status"] == "expired"
    finally:
        if draft_id is not None:
            async with factory() as db:
                await db.execute(
                    text("DELETE FROM load_workspace_drafts WHERE id = :id"),
                    {"id": draft_id},
                )
                await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_creates_commercial_evidence_when_pdf_ready() -> None:
    engine, factory = _session()
    draft_id = None
    load_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={**SAMPLE_DRAFT_JSON, "loadNumber": f"EV-{uuid.uuid4().hex[:8]}"},
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
            await db.execute(
                text(
                    """
                    UPDATE load_workspace_drafts
                    SET pdf_upload_state = 'ready',
                        pdf_storage_key = 'pytest/fake-rate-con.pdf',
                        pdf_sha256 = 'abc123',
                        pdf_filename = 'rate-con.pdf',
                        accepted_parse_json = '{"document":{"filename":"rate-con.pdf"},"extracted":{},"raw_text":"line1","warnings":[]}'::jsonb,
                        accepted_parse_schema_version = 'load_document_parse_response_v1',
                        accepted_parse_pdf_sha256 = 'abc123'
                    WHERE tenant_id = :tenant_id AND id = :id
                    """
                ),
                {"tenant_id": tenant_id, "id": draft_id},
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
                    promotion_idempotency_key=f"ev-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id

        async with factory() as db:
            count = await db.scalar(
                text(
                    "SELECT COUNT(*) FROM load_commercial_evidence WHERE load_id = :lid AND workspace_draft_id = :did"
                ),
                {"lid": load_id, "did": draft_id},
            )
            assert int(count or 0) == 1
    finally:
        if load_id is not None or draft_id is not None:
            async with factory() as db:
                if load_id is not None:
                    await db.execute(text("DELETE FROM load_stops WHERE load_id = :id"), {"id": load_id})
                    await db.execute(
                        text("DELETE FROM load_commercial_evidence WHERE load_id = :id"),
                        {"id": load_id},
                    )
                    await db.execute(
                        text(
                            "UPDATE loads SET promotion_origin_workspace_draft_id = NULL WHERE id = :id"
                        ),
                        {"id": load_id},
                    )
                    await db.execute(text("DELETE FROM loads WHERE id = :id"), {"id": load_id})
                if draft_id is not None:
                    await db.execute(
                        text("DELETE FROM load_workspace_drafts WHERE id = :id"),
                        {"id": draft_id},
                    )
                await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_promotion_idempotency_key_conflict_across_drafts() -> None:
    engine, factory = _session()
    draft_a_id = draft_b_id = None
    load_id = None
    shared_key = f"shared-{uuid.uuid4().hex}"
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            draft_a = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={**SAMPLE_DRAFT_JSON, "loadNumber": f"A-{uuid.uuid4().hex[:6]}"},
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_a_id = draft_a.id
            draft_b = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={**SAMPLE_DRAFT_JSON, "loadNumber": f"B-{uuid.uuid4().hex[:6]}"},
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_b_id = draft_b.id

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            first = await promote_workspace_draft(
                db,
                tenant_id,
                draft_a_id,
                LoadWorkspaceDraftPromote(expected_concurrency_version=1, promotion_idempotency_key=shared_key),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = first.load_id

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            with pytest.raises(HTTPException) as exc:
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_b_id,
                    LoadWorkspaceDraftPromote(expected_concurrency_version=1, promotion_idempotency_key=shared_key),
                    promoted_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "LOAD_WORKSPACE_DRAFT_PROMOTION_IDEMPOTENCY_KEY_CONFLICT"
    finally:
        async with factory() as db:
            if load_id is not None:
                await db.execute(text("DELETE FROM load_stops WHERE load_id = :id"), {"id": load_id})
                await db.execute(
                    text("DELETE FROM load_commercial_evidence WHERE load_id = :id"),
                    {"id": load_id},
                )
                await db.execute(
                    text("UPDATE loads SET promotion_origin_workspace_draft_id = NULL WHERE id = :id"),
                    {"id": load_id},
                )
            for did in (draft_a_id, draft_b_id):
                if did is not None:
                    await db.execute(
                        text("DELETE FROM load_workspace_drafts WHERE id = :id"),
                        {"id": did},
                    )
            if load_id is not None:
                await db.execute(text("DELETE FROM loads WHERE id = :id"), {"id": load_id})
            await db.commit()
        await engine.dispose()


async def _scalar_count(sql: str) -> int:
    engine, factory = _session()
    try:
        async with factory() as db:
            return int(await db.scalar(text(sql)))
    finally:
        await engine.dispose()
