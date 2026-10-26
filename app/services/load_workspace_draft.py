"""Load workspace draft persistence (commercial pre-promotion workspace)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency.draft_conflicts import workspace_draft_version_conflict_exception
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.schemas.load_workspace_draft import (
    LoadWorkspaceDraftCreate,
    LoadWorkspaceDraftUpdate,
)
from app.services.load_workspace_draft_lifecycle import (
    apply_expiry_if_overdue,
    require_workspace_draft_open_for_mutation,
)

DEFAULT_DRAFT_TTL_DAYS = 7
EDITABLE_STATUS = "draft"


class LoadWorkspaceDraftError(Exception):
    def __init__(self, message: str, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def merge_origin_draft_parse_manual_override_keys(
    db: AsyncSession,
    tenant_id: int,
    draft_id: uuid.UUID,
    keys: list[str],
) -> None:
    """Persist operator parse-field edits on promoted workspace draft_json (no status gate)."""
    from app.services.load_workspace_draft_mapper import (
        ALLOWED_PARSE_MANUAL_OVERRIDE_KEYS,
        PARSE_MANUAL_OVERRIDE_KEYS_DRAFT_FIELD,
    )

    current = await get_workspace_draft(db, tenant_id, draft_id)
    if current is None:
        return
    sanitized = [k for k in keys if k in ALLOWED_PARSE_MANUAL_OVERRIDE_KEYS]
    merged = dict(current.draft_json or {})
    merged[PARSE_MANUAL_OVERRIDE_KEYS_DRAFT_FIELD] = sanitized
    await db.execute(
        update(LoadWorkspaceDraft)
        .where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
        .values(draft_json=merged, updated_at=func.now())
    )


async def get_workspace_draft(
    db: AsyncSession, tenant_id: int, draft_id: uuid.UUID
) -> LoadWorkspaceDraft | None:
    return await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )


async def create_workspace_draft(
    db: AsyncSession,
    tenant_id: int,
    payload: LoadWorkspaceDraftCreate,
    *,
    created_by_platform_user_id: str | None,
) -> LoadWorkspaceDraft:
    now = datetime.now(timezone.utc)
    row = LoadWorkspaceDraft(
        tenant_id=tenant_id,
        status=EDITABLE_STATUS,
        draft_schema_version=1,
        draft_json=payload.draft_json,
        source_channel=payload.source_channel,
        created_by_platform_user_id=created_by_platform_user_id,
        updated_by_platform_user_id=created_by_platform_user_id,
        expires_at=now + timedelta(days=DEFAULT_DRAFT_TTL_DAYS),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_workspace_draft(
    db: AsyncSession,
    tenant_id: int,
    draft_id: uuid.UUID,
    payload: LoadWorkspaceDraftUpdate,
    *,
    updated_by_platform_user_id: str | None,
) -> LoadWorkspaceDraft:
    current = await get_workspace_draft(db, tenant_id, draft_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    await require_workspace_draft_open_for_mutation(db, current)
    server_version = int(current.concurrency_version)

    stmt = (
        update(LoadWorkspaceDraft)
        .where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
            LoadWorkspaceDraft.status == EDITABLE_STATUS,
            LoadWorkspaceDraft.concurrency_version == payload.expected_concurrency_version,
        )
        .values(
            draft_json=payload.draft_json,
            concurrency_version=LoadWorkspaceDraft.concurrency_version + 1,
            updated_by_platform_user_id=updated_by_platform_user_id,
            updated_at=func.now(),
        )
        .returning(LoadWorkspaceDraft)
    )
    result = await db.execute(stmt)
    updated = result.scalar_one_or_none()
    if updated is None:
        await db.rollback()
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=payload.expected_concurrency_version,
            server_version=server_version,
        )
    await db.commit()
    await db.refresh(updated)
    return updated


async def list_workspace_drafts(
    db: AsyncSession,
    tenant_id: int,
    *,
    status: str = EDITABLE_STATUS,
    page: int = 1,
    size: int = 50,
) -> tuple[list[LoadWorkspaceDraft], int]:
    """List workspace drafts for a tenant (default: editable ``draft`` status)."""
    normalized_status = (status or EDITABLE_STATUS).strip().lower()
    page = max(1, int(page))
    size = min(100, max(1, int(size)))
    offset = (page - 1) * size

    filters = (
        LoadWorkspaceDraft.tenant_id == tenant_id,
        LoadWorkspaceDraft.status == normalized_status,
    )
    total = int(
        await db.scalar(select(func.count()).where(*filters)) or 0
    )
    rows = (
        await db.scalars(
            select(LoadWorkspaceDraft)
            .where(*filters)
            .order_by(LoadWorkspaceDraft.updated_at.desc())
            .offset(offset)
            .limit(size)
        )
    ).all()
    return list(rows), total
