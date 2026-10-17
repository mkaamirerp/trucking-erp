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

DEFAULT_DRAFT_TTL_DAYS = 7
EDITABLE_STATUS = "draft"


class LoadWorkspaceDraftError(Exception):
    def __init__(self, message: str, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


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
    server_version = int(current.concurrency_version)
    if current.status != EDITABLE_STATUS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOAD_WORKSPACE_DRAFT_NOT_EDITABLE",
                "status": current.status,
            },
        )

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
