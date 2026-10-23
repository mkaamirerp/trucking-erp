"""Load workspace draft application layer (service + optional HTTP on demo clone)."""

from __future__ import annotations

import asyncio
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
from app.core.integration_db_guard import database_name_from_url
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.services.loads import get_load
from app.services.load_workspace_draft_promotion import PromotionResult, promote_workspace_draft
from sqlalchemy import update as sa_update
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


def _promotable_draft_json(**overrides: object) -> dict:
    base = {
        **SAMPLE_DRAFT_JSON,
        "brokerLoadReference": "PROMO-REF-001",
        "draftStops": [
            {"stopType": "PICKUP", "city": "Toronto", "stateOrProvince": "ON"},
            {"stopType": "DELIVERY", "city": "Montreal", "stateOrProvince": "QC"},
        ],
    }
    base.update(overrides)
    return base

ACCEPTED_PARSE_BROKER_REF_ONLY = {
    "document": {"filename": "ratecon.pdf"},
    "raw_text": "",
    "warnings": [],
    "field_confidence": {},
    "extracted": {
        "broker_load_reference": "3872125-1",
        "references": [],
        "stops": [],
    },
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
async def test_promote_fills_broker_load_reference_from_accepted_parse_json() -> None:
    if database_name_from_url(_tenant_async_url()) == "tenant_demo":
        pytest.skip("mutation tests must not run on tenant_demo")
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
                    draft_json=_promotable_draft_json(
                        loadNumber=f"REF-PARSE-{uuid.uuid4().hex[:8]}",
                        brokerLoadReference="",
                    ),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
            await db.execute(
                sa_update(LoadWorkspaceDraft)
                .where(LoadWorkspaceDraft.tenant_id == tenant_id, LoadWorkspaceDraft.id == draft_id)
                .values(accepted_parse_json=ACCEPTED_PARSE_BROKER_REF_ONLY)
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
                    promotion_idempotency_key=f"promo-ref-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id
            load = await get_load(db, tenant_id, load_id)
            assert load is not None
            assert load.broker_load_reference == "3872125-1"
            assert load.status == "ready"
    finally:
        await _delete_promoted_load_and_draft(factory, load_id, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_creates_ready_load() -> None:
    if database_name_from_url(_tenant_async_url()) == "tenant_demo":
        pytest.skip("mutation tests must not run on tenant_demo")
    engine, factory = _session()
    draft_id = None
    load_id = None
    try:
        tenant_id, draft_id = await _create_draft(
            factory,
            _promotable_draft_json(loadNumber=f"READY-{uuid.uuid4().hex[:8]}"),
        )
        async with factory() as db:
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=f"promo-ready-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id
            load = await get_load(db, tenant_id, load_id)
            assert load is not None
            assert load.status == "ready"
    finally:
        await _delete_promoted_load_and_draft(factory, load_id, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_rejects_missing_load_number_or_po_creates_no_load() -> None:
    if database_name_from_url(_tenant_async_url()) == "tenant_demo":
        pytest.skip("mutation tests must not run on tenant_demo")
    engine, factory = _session()
    draft_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json=_promotable_draft_json(
                        loadNumber="",
                        brokerLoadReference="",
                        loadReferences=[],
                    ),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            with pytest.raises(HTTPException) as exc:
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"promo-noref-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 400
            detail = exc.value.detail
            assert isinstance(detail, dict)
            assert detail.get("code") == "LOAD_READY_PREREQUISITES_NOT_MET"
            loads_after = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
            assert loads_after == loads_before
            row = (
                await db.execute(
                    text("SELECT status, promoted_load_id FROM load_workspace_drafts WHERE id = :id"),
                    {"id": draft_id},
                )
            ).one()
            assert row.status == "draft"
            assert row.promoted_load_id is None
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
                    draft_json=_promotable_draft_json(loadNumber=f"PROMO-{uuid.uuid4().hex[:8]}"),
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
                    draft_json=_promotable_draft_json(loadNumber=f"EV-{uuid.uuid4().hex[:8]}"),
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
                    if await db.scalar(text("SELECT to_regclass('public.load_pod_evidence')")):
                        await db.execute(
                            text("DELETE FROM load_pod_evidence WHERE load_id = :id"),
                            {"id": load_id},
                        )
                    await db.execute(text("DELETE FROM load_stops WHERE load_id = :id"), {"id": load_id})
                    await db.execute(
                        text("DELETE FROM load_commercial_evidence WHERE load_id = :id"),
                        {"id": load_id},
                    )
                if load_id is not None:
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
                    draft_json=_promotable_draft_json(loadNumber=f"A-{uuid.uuid4().hex[:6]}"),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_a_id = draft_a.id
            draft_b = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json=_promotable_draft_json(loadNumber=f"B-{uuid.uuid4().hex[:6]}"),
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


@pytest.mark.asyncio
async def test_concurrent_promote_competing_idempotency_keys_one_load() -> None:
    """Two simultaneous promotions on one draft with different keys: one Load, one 409."""
    engine, factory = _session()
    draft_id = None
    load_id = None
    tenant_id = 0
    key_a = f"concurrent-a-{uuid.uuid4().hex}"
    key_b = f"concurrent-b-{uuid.uuid4().hex}"
    load_number = f"DW-CONC-{uuid.uuid4().hex[:10]}"
    try:
        tenant_id, draft_id = await _create_draft(
            factory,
            _promotable_draft_json(loadNumber=load_number),
        )

        async def _promote(key: str):
            async with factory() as db:
                return await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=key,
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )

        outcomes = await asyncio.gather(_promote(key_a), _promote(key_b), return_exceptions=True)
        successes = [o for o in outcomes if isinstance(o, PromotionResult)]
        failures = [o for o in outcomes if isinstance(o, HTTPException)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert successes[0].idempotent_replay is False
        load_id = int(successes[0].load_id)
        assert failures[0].status_code == 409
        assert failures[0].detail["code"] == "LOAD_WORKSPACE_DRAFT_ALREADY_PROMOTED"
        assert int(failures[0].detail["promoted_load_id"]) == load_id

        winning_key = key_a if successes[0].draft.promotion_idempotency_key == key_a else key_b
        assert successes[0].draft.promotion_idempotency_key == winning_key
        assert winning_key in (key_a, key_b)

        async with factory() as db:
            load_count = int(
                await db.scalar(
                    text(
                        "SELECT count(*)::int FROM loads WHERE tenant_id = :t "
                        "AND promotion_origin_workspace_draft_id = :d"
                    ),
                    {"t": tenant_id, "d": draft_id},
                )
                or 0
            )
            assert load_count == 1
            trip_load_count = int(
                await db.scalar(
                    text(
                        "SELECT count(*)::int FROM trip_loads tl "
                        "INNER JOIN loads l ON l.tenant_id = tl.tenant_id AND l.id = tl.load_id "
                        "WHERE l.tenant_id = :t AND l.promotion_origin_workspace_draft_id = :d"
                    ),
                    {"t": tenant_id, "d": draft_id},
                )
                or 0
            )
            assert trip_load_count == 0
            evidence_count = int(
                await db.scalar(
                    text(
                        "SELECT count(*)::int FROM load_commercial_evidence "
                        "WHERE tenant_id = :t AND workspace_draft_id = :d"
                    ),
                    {"t": tenant_id, "d": draft_id},
                )
                or 0
            )
            assert evidence_count == 0
            audit_count = int(
                await db.scalar(
                    text(
                        "SELECT count(*)::int FROM audit_events WHERE tenant_id = :t AND module = 'loads' "
                        "AND entity_type = 'load' AND entity_id = :e AND action = 'load_created'"
                    ),
                    {"t": tenant_id, "e": str(load_id)},
                )
                or 0
            )
            assert audit_count == 1
            draft_status = await db.scalar(
                text("SELECT status FROM load_workspace_drafts WHERE tenant_id = :t AND id = :d"),
                {"t": tenant_id, "d": draft_id},
            )
            assert draft_status == "promoted"
    finally:
        async with factory() as db:
            if load_id is not None:
                await db.execute(
                    text("DELETE FROM audit_events WHERE tenant_id = :t AND module = 'loads' AND entity_id = :e"),
                    {"t": tenant_id, "e": str(load_id)},
                )
                await db.commit()
        await _delete_promoted_load_and_draft(factory, load_id, draft_id)
        await engine.dispose()


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


async def _create_draft(factory, draft_json: dict):
    async with factory() as db:
        tenant_id = await _resolve_tenant_id(db)
        draft = await create_workspace_draft(
            db,
            tenant_id,
            LoadWorkspaceDraftCreate(source_channel="manual", draft_json=draft_json),
            created_by_platform_user_id="integration-test-user",
        )
        return tenant_id, draft.id


async def _assert_rejected_promotion_left_draft_promotable(factory, tenant_id: int, draft_id, loads_before: int):
    async with factory() as db:
        assert await db.scalar(text("SELECT COUNT(*) FROM loads")) == loads_before
        row = (
            await db.execute(
                text(
                    "SELECT status, concurrency_version, promoted_load_id FROM load_workspace_drafts "
                    "WHERE tenant_id = :t AND id = :id"
                ),
                {"t": tenant_id, "id": draft_id},
            )
        ).one()
        assert (row.status, int(row.concurrency_version), row.promoted_load_id) == ("draft", 1, None)


@pytest.mark.asyncio
async def test_promote_persists_commercial_stops_through_shared_insert() -> None:
    engine, factory = _session()
    draft_id = load_id = None
    try:
        draft_json = _promotable_draft_json(
            loadNumber=f"PROMO-STOPS-{uuid.uuid4().hex[:8]}",
            draftStops=[
                {"stopType": "PICKUP", "city": "Toronto", "stateOrProvince": "ON", "facilityName": "Origin DC"},
                {"stopType": "DELIVERY", "city": "Boston", "stateOrProvince": "MA", "sequence": 4},
            ],
        )
        tenant_id, draft_id = await _create_draft(factory, draft_json)
        async with factory() as db:
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=f"promo-stops-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id

        async with factory() as db:
            load_row = (
                await db.execute(
                    text("SELECT status, tenant_id, promotion_origin_workspace_draft_id FROM loads WHERE id = :id"),
                    {"id": load_id},
                )
            ).one()
            assert load_row.status == "ready"
            assert int(load_row.tenant_id) == tenant_id
            assert str(load_row.promotion_origin_workspace_draft_id) == str(draft_id)
            stops = (
                await db.execute(
                    text(
                        "SELECT tenant_id, stop_type, sequence, city, facility_name FROM load_stops "
                        "WHERE load_id = :id ORDER BY sequence"
                    ),
                    {"id": load_id},
                )
            ).all()
            assert [(int(s.tenant_id), s.stop_type, s.sequence, s.city, s.facility_name) for s in stops] == [
                (tenant_id, "PICKUP", 0, "Toronto", "Origin DC"),
                (tenant_id, "DELIVERY", 4, "Boston", None),
            ]
    finally:
        await _delete_promoted_load_and_draft(factory, load_id, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_rejects_unknown_broker_without_load_or_draft_change() -> None:
    engine, factory = _session()
    draft_id = None
    try:
        async with factory() as db:
            missing_broker_id = int(await db.scalar(text("SELECT COALESCE(MAX(id), 0) + 100000 FROM brokers")))
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
        tenant_id, draft_id = await _create_draft(
            factory,
            _promotable_draft_json(
                loadNumber=f"PROMO-BRK-{uuid.uuid4().hex[:8]}",
                brokerId=missing_broker_id,
            ),
        )
        async with factory() as db:
            with pytest.raises(HTTPException) as exc:
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"promo-brk-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 400
            assert exc.value.detail == "Broker not found"
            await db.rollback()
        await _assert_rejected_promotion_left_draft_promotable(factory, tenant_id, draft_id, loads_before)
    finally:
        await _delete_promoted_load_and_draft(factory, None, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_rejects_contact_of_other_broker_like_api_create() -> None:
    engine, factory = _session()
    draft_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            pair = (
                await db.execute(
                    text(
                        "SELECT bc.id AS contact_id, b.id AS other_broker_id FROM broker_contacts bc "
                        "JOIN brokers b ON b.tenant_id = bc.tenant_id AND b.id <> bc.broker_id "
                        "WHERE bc.tenant_id = :t ORDER BY bc.id, b.id LIMIT 1"
                    ),
                    {"t": tenant_id},
                )
            ).one_or_none()
            if pair is None:
                pytest.skip("tenant has no broker contact plus a second broker")
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
        _, draft_id = await _create_draft(
            factory,
            _promotable_draft_json(
                loadNumber=f"PROMO-CON-{uuid.uuid4().hex[:8]}",
                brokerId=int(pair.other_broker_id),
                brokerContactId=int(pair.contact_id),
            ),
        )
        async with factory() as db:
            with pytest.raises(HTTPException) as exc:
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"promo-con-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 400
            assert exc.value.detail == "Broker contact must belong to the selected broker"
            await db.rollback()
        await _assert_rejected_promotion_left_draft_promotable(factory, tenant_id, draft_id, loads_before)
    finally:
        await _delete_promoted_load_and_draft(factory, None, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_rejects_duplicate_load_number_without_promoting() -> None:
    engine, factory = _session()
    draft_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            existing_number = await db.scalar(
                text("SELECT load_number FROM loads WHERE tenant_id = :t ORDER BY id LIMIT 1"), {"t": tenant_id}
            )
            if existing_number is None:
                pytest.skip("tenant has no existing Load")
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
        _, draft_id = await _create_draft(factory, _promotable_draft_json(loadNumber=existing_number))
        async with factory() as db:
            with pytest.raises(HTTPException) as exc:
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"promo-dup-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 400
            assert exc.value.detail == "A load with this load_number already exists"
            await db.rollback()
        await _assert_rejected_promotion_left_draft_promotable(factory, tenant_id, draft_id, loads_before)
    finally:
        await _delete_promoted_load_and_draft(factory, None, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_writes_one_load_created_audit_and_replay_adds_none() -> None:
    engine, factory = _session()
    draft_id = load_id = None
    try:
        tenant_id, draft_id = await _create_draft(
            factory, _promotable_draft_json(loadNumber=f"PROMO-AUD-{uuid.uuid4().hex[:8]}")
        )
        promo_key = f"promo-aud-{uuid.uuid4().hex}"
        promote_payload = LoadWorkspaceDraftPromote(expected_concurrency_version=1, promotion_idempotency_key=promo_key)
        async with factory() as db:
            result = await promote_workspace_draft(
                db, tenant_id, draft_id, promote_payload, promoted_by_platform_user_id="integration-test-user"
            )
            load_id = result.load_id
            replay = await promote_workspace_draft(
                db, tenant_id, draft_id, promote_payload, promoted_by_platform_user_id="integration-test-user"
            )
            assert replay.idempotent_replay is True

        async with factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT source, context_json FROM audit_events WHERE tenant_id = :t AND module = 'loads' "
                        "AND entity_type = 'load' AND entity_id = :e AND action = 'load_created'"
                    ),
                    {"t": tenant_id, "e": str(load_id)},
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].source == "ui"
            assert rows[0].context_json == {
                "origin": "workspace_draft_promotion",
                "workspace_draft_id": str(draft_id),
                "promotion_idempotency_key": promo_key,
            }
    finally:
        async with factory() as db:
            if load_id is not None:
                await db.execute(
                    text("DELETE FROM audit_events WHERE tenant_id = :t AND module = 'loads' AND entity_id = :e"),
                    {"t": tenant_id, "e": str(load_id)},
                )
                await db.commit()
        await _delete_promoted_load_and_draft(factory, load_id, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_audit_failure_rolls_back_load_and_keeps_draft_promotable(monkeypatch) -> None:
    import app.services.audit_events as audit_events

    engine, factory = _session()
    draft_id = None
    load_number = f"PROMO-AUDFAIL-{uuid.uuid4().hex[:8]}"
    try:
        async with factory() as db:
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
        tenant_id, draft_id = await _create_draft(
            factory,
            _promotable_draft_json(loadNumber=load_number),
        )

        async def _failing_audit(*_a, **_k):
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_events, "write_audit_event", _failing_audit)
        async with factory() as db:
            with pytest.raises(RuntimeError, match="audit store unavailable"):
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"promo-audfail-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            await db.rollback()
        monkeypatch.undo()

        await _assert_rejected_promotion_left_draft_promotable(factory, tenant_id, draft_id, loads_before)
        async with factory() as db:
            assert await db.scalar(
                text("SELECT COUNT(*) FROM loads WHERE tenant_id = :t AND load_number = :n"),
                {"t": tenant_id, "n": load_number},
            ) == 0
            assert await db.scalar(
                text("SELECT COUNT(*) FROM load_commercial_evidence WHERE workspace_draft_id = :id"),
                {"id": draft_id},
            ) == 0
    finally:
        await _delete_promoted_load_and_draft(factory, None, draft_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_shared_insert_leaves_nothing_when_caller_rolls_back() -> None:
    from app.schemas.load import LoadCreate
    from app.services.loads import _insert_commercial_load_uncommitted

    engine, factory = _session()
    load_number = f"SHARED-RB-{uuid.uuid4().hex[:8]}"
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            load, stop_diff = await _insert_commercial_load_uncommitted(
                db,
                tenant_id,
                LoadCreate(load_number=load_number, stops=[{"stop_type": "PICKUP", "city": "Albany"}]),
            )
            assert load.id is not None
            assert len(stop_diff["added"]) == 1
            await db.rollback()
        async with factory() as db:
            assert await db.scalar(
                text("SELECT COUNT(*) FROM loads WHERE load_number = :n"), {"n": load_number}
            ) == 0
    finally:
        async with factory() as db:
            await db.execute(
                text("DELETE FROM load_stops WHERE load_id IN (SELECT id FROM loads WHERE load_number = :n)"),
                {"n": load_number},
            )
            await db.execute(text("DELETE FROM loads WHERE load_number = :n"), {"n": load_number})
            await db.commit()
        await engine.dispose()


async def _scalar_count(sql: str) -> int:
    engine, factory = _session()
    try:
        async with factory() as db:
            return int(await db.scalar(text(sql)))
    finally:
        await engine.dispose()
