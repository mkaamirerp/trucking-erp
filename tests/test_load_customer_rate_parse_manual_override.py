"""Customer rate parse manual-override persistence (draft_json + promoted load origin draft)."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.schemas.load import LoadUpdate
from app.schemas.load_workspace_draft import LoadWorkspaceDraftCreate
from app.services.load_workspace_draft import create_workspace_draft, get_workspace_draft
from app.services.load_workspace_draft_mapper import parse_manual_override_keys_from_draft_json
from app.services.load_workspace_draft_promotion import promote_workspace_draft
from app.schemas.load_workspace_draft import LoadWorkspaceDraftPromote
from app.services.loads import get_load, get_load_parse_manual_override_keys, update_load

from tests.test_load_workspace_draft_api import _promotable_draft_json, _resolve_tenant_id, _session

REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))

pytestmark = pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL not configured")


@pytest.mark.asyncio
async def test_draft_json_persists_customer_rate_manual_override_keys() -> None:
    engine, factory = _session()
    draft_id = None
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={
                        **_promotable_draft_json(loadNumber=f"CR-{uuid.uuid4().hex[:8]}"),
                        "rate": "2000",
                        "customerRate": "1800",
                        "parseManualOverrideKeys": ["customerRate"],
                    },
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
            keys = parse_manual_override_keys_from_draft_json(draft.draft_json)
            assert keys == ["customerRate"]
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
async def test_promoted_load_patch_syncs_parse_manual_override_keys_to_origin_draft() -> None:
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
                        loadNumber=f"CR-P-{uuid.uuid4().hex[:8]}",
                        rate="2000",
                        customerRate="1500",
                    ),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            promo = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=f"cr-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = promo.load_id

        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            load = await get_load(db, tenant_id, load_id)
            assert load is not None
            assert float(load.customer_rate) == 1500
            updated = await update_load(
                db,
                tenant_id,
                load_id,
                LoadUpdate(
                    expected_concurrency_version=load.concurrency_version,
                    customer_rate="1800",
                    parse_manual_override_keys=["customerRate"],
                ),
                actor_user_id=1,
            )
            assert float(updated.customer_rate) == 1800
            origin = await get_workspace_draft(db, tenant_id, draft_id)
            assert origin is not None
            assert parse_manual_override_keys_from_draft_json(origin.draft_json) == ["customerRate"]
            enriched = await get_load_parse_manual_override_keys(db, tenant_id, updated)
            assert enriched == ["customerRate"]
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
