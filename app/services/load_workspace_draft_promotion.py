"""Promote a load workspace draft into one commercial Load (atomic, idempotent)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency.draft_conflicts import workspace_draft_version_conflict_exception
from app.models.load import Load, LoadStop
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.schemas.load import LoadCreate
from app.schemas.load_workspace_draft import LoadWorkspaceDraftPromote
from app.services.load_workspace_draft_mapper import draft_json_to_load_create
from app.services.loads import (
    _COMMERCIAL_STOP_ATTRS,
    _ensure_unique_load_number,
    _get_broker,
    _get_broker_contact,
    _get_customs_broker,
    _guard_create_payload,
    _load_data_from_payload,
    _validate_stops_write_payload,
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
    if draft.promotion_idempotency_key == key and draft.status == "draft":
        # Another in-flight attempt may have failed after setting the key; treat as conflict.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "LOAD_WORKSPACE_DRAFT_PROMOTION_IN_PROGRESS"},
        )
    existing = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.promotion_idempotency_key == key,
            LoadWorkspaceDraft.status == "promoted",
        )
    )
    if existing is not None and existing.promoted_load_id is not None:
        return PromotionResult(
            draft=existing, load_id=int(existing.promoted_load_id), idempotent_replay=True
        )
    return None


async def _insert_load_from_create(
    db: AsyncSession,
    tenant_id: int,
    payload: LoadCreate,
    *,
    promotion_origin_workspace_draft_id: uuid.UUID,
) -> Load:
    _guard_create_payload(payload)
    if payload.broker_id is not None and not await _get_broker(db, tenant_id, payload.broker_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker not found")
    if payload.broker_contact_id is not None:
        contact = await _get_broker_contact(db, tenant_id, payload.broker_contact_id)
        if not contact:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker contact not found")
        if payload.broker_id is not None and contact.broker_id != payload.broker_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Broker contact must belong to the selected broker",
            )
    if payload.customs_broker_id is not None and not await _get_customs_broker(
        db, tenant_id, payload.customs_broker_id
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customs broker not found")

    load_number = payload.load_number or f"DRAFT-{uuid.uuid4().hex[:8].upper()}"
    await _ensure_unique_load_number(db, tenant_id, load_number)

    data = _load_data_from_payload(payload)
    data["load_number"] = load_number
    data["status"] = "draft"

    load = Load(
        **data,
        tenant_id=tenant_id,
        promotion_origin_workspace_draft_id=promotion_origin_workspace_draft_id,
    )
    db.add(load)
    await db.flush()

    if payload.stops:
        _validate_stops_write_payload(payload.stops)
        for i, stop_in in enumerate(payload.stops):
            stop_data = stop_in.model_dump(exclude={"id"}, exclude_unset=False)
            for k in list(stop_data.keys()):
                if k not in _COMMERCIAL_STOP_ATTRS and k != "sequence":
                    stop_data.pop(k, None)
            stop_data["sequence"] = stop_in.sequence if stop_in.sequence is not None else i
            db.add(LoadStop(tenant_id=tenant_id, load_id=load.id, **stop_data))

    await db.flush()
    return load


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

    if draft.status != "draft":
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

    load_create = draft_json_to_load_create(draft.draft_json or {})
    now = datetime.now(timezone.utc)

    load = await _insert_load_from_create(
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
        source="workspace_draft_promotion",
        changed_fields=None,
        context_json={"workspace_draft_id": str(draft.id), "promotion_idempotency_key": payload.promotion_idempotency_key},
    )

    await db.commit()
    await db.refresh(draft)
    return PromotionResult(draft=draft, load_id=int(load.id), idempotent_replay=False)
