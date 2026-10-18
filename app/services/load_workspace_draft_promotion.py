"""Promote a load workspace draft into one commercial Load (atomic, idempotent)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency.draft_conflicts import workspace_draft_version_conflict_exception
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.schemas.load_workspace_draft import LoadWorkspaceDraftPromote
from app.services.load_workspace_draft_lifecycle import apply_expiry_if_overdue, raise_not_editable
from app.services.load_workspace_draft_mapper import DraftJsonMappingError, draft_json_to_load_create
from app.services.loads import (
    _insert_commercial_load_uncommitted,
    _write_load_audit,
    get_load,
)


class PromotionResult:
    def __init__(self, *, draft: LoadWorkspaceDraft, load_id: int, idempotent_replay: bool) -> None:
        self.draft = draft
        self.load_id = load_id
        self.idempotent_replay = idempotent_replay


async def _idempotent_replay(
    db: AsyncSession, tenant_id: int, draft: LoadWorkspaceDraft, key: str
) -> PromotionResult | None:
    if draft.status == "promoted" and draft.promoted_load_id is not None:
        if draft.promotion_idempotency_key == key:
            return PromotionResult(draft=draft, load_id=int(draft.promoted_load_id), idempotent_replay=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOAD_WORKSPACE_DRAFT_ALREADY_PROMOTED",
                "promoted_load_id": draft.promoted_load_id,
            },
        )
    key_owner = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.promotion_idempotency_key == key,
        )
    )
    if key_owner is not None and key_owner.id != draft.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOAD_WORKSPACE_DRAFT_PROMOTION_IDEMPOTENCY_KEY_CONFLICT",
                "owner_draft_id": str(key_owner.id),
            },
        )
    return None


def _maybe_commercial_evidence_row(
    draft: LoadWorkspaceDraft,
    *,
    tenant_id: int,
    load_id: int,
    promoted_by_platform_user_id: str | None,
    promoted_at: datetime,
) -> LoadCommercialEvidence | None:
    if draft.pdf_upload_state != "ready":
        return None
    if not draft.pdf_storage_key or not draft.pdf_sha256:
        return None
    return LoadCommercialEvidence(
        tenant_id=tenant_id,
        load_id=load_id,
        workspace_draft_id=draft.id,
        file_sha256=draft.pdf_sha256,
        storage_key=draft.pdf_storage_key,
        filename=draft.pdf_filename,
        accepted_parse_json=draft.accepted_parse_json or {},
        parse_schema_version=draft.accepted_parse_schema_version,
        promoted_by_platform_user_id=promoted_by_platform_user_id,
        promoted_at=promoted_at,
    )


async def promote_workspace_draft(
    db: AsyncSession,
    tenant_id: int,
    draft_id: uuid.UUID,
    payload: LoadWorkspaceDraftPromote,
    *,
    promoted_by_platform_user_id: str | None,
) -> PromotionResult:
    draft = await db.scalar(
        select(LoadWorkspaceDraft)
        .where(LoadWorkspaceDraft.tenant_id == tenant_id, LoadWorkspaceDraft.id == draft_id)
        .with_for_update()
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")

    replay = await _idempotent_replay(db, tenant_id, draft, payload.promotion_idempotency_key)
    if replay is not None:
        return replay

    await apply_expiry_if_overdue(db, draft)
    if draft.status != "draft":
        if draft.status in {"discarded", "expired"}:
            raise_not_editable(draft)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "LOAD_WORKSPACE_DRAFT_NOT_PROMOTABLE", "status": draft.status},
        )
    if int(draft.concurrency_version) != payload.expected_concurrency_version:
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=payload.expected_concurrency_version,
            server_version=int(draft.concurrency_version),
        )

    try:
        load_create = draft_json_to_load_create(draft.draft_json or {})
    except DraftJsonMappingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "LOAD_WORKSPACE_DRAFT_MAPPING_INVALID", "field": exc.field, "message": str(exc)},
        ) from exc
    now = datetime.now(timezone.utc)

    load, _stop_create_diff = await _insert_commercial_load_uncommitted(
        db,
        tenant_id,
        load_create,
        promotion_origin_workspace_draft_id=draft.id,
    )

    evidence = _maybe_commercial_evidence_row(
        draft,
        tenant_id=tenant_id,
        load_id=int(load.id),
        promoted_by_platform_user_id=promoted_by_platform_user_id,
        promoted_at=now,
    )
    if evidence is not None:
        db.add(evidence)

    draft.status = "promoted"
    draft.promoted_load_id = int(load.id)
    draft.promoted_at = now
    draft.promotion_idempotency_key = payload.promotion_idempotency_key
    draft.concurrency_version = int(draft.concurrency_version) + 1
    draft.updated_by_platform_user_id = promoted_by_platform_user_id

    await db.flush()

    hydrated = await get_load(db, tenant_id, int(load.id))
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Load missing after promotion")
    await _write_load_audit(
        db,
        tenant_id=tenant_id,
        load=hydrated,
        action="load_created",
        actor_user_id=None,
        request_id=None,
        correlation_id=None,
        source="ui",
        changed_fields=None,
        context_json={
            "origin": "workspace_draft_promotion",
            "workspace_draft_id": str(draft.id),
            "promotion_idempotency_key": payload.promotion_idempotency_key,
        },
        best_effort=False,
    )

    await db.commit()
    await db.refresh(draft)
    return PromotionResult(draft=draft, load_id=int(load.id), idempotent_replay=False)
