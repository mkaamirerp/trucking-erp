"""Load workspace drafts — commercial fields before Load promotion."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.enforce import require_pilot_capability
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.load_workspace_draft import (
    LoadWorkspaceDraftCreate,
    LoadWorkspaceDraftOut,
    LoadWorkspaceDraftUpdate,
)
from app.services import load_workspace_draft as draft_service

router = APIRouter(prefix="/load-workspace-drafts", tags=["load-workspace-drafts"])


def _platform_user_id(user: CurrentUser) -> str:
    return str(user.user_id)


@router.post("", response_model=LoadWorkspaceDraftOut, status_code=status.HTTP_201_CREATED)
async def create_load_workspace_draft(
    payload: LoadWorkspaceDraftCreate,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    _auth=Depends(require_pilot_capability("loads.records", "create")),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftOut:
    row = await draft_service.create_workspace_draft(
        db,
        tenant_id,
        payload,
        created_by_platform_user_id=_platform_user_id(user),
    )
    return LoadWorkspaceDraftOut.model_validate(row)


@router.get("/{draft_id}", response_model=LoadWorkspaceDraftOut)
async def get_load_workspace_draft(
    draft_id: uuid.UUID,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    _auth=Depends(require_pilot_capability("loads.records", "view")),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftOut:
    row = await draft_service.get_workspace_draft(db, tenant_id, draft_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    return LoadWorkspaceDraftOut.model_validate(row)


@router.patch("/{draft_id}", response_model=LoadWorkspaceDraftOut)
async def update_load_workspace_draft(
    draft_id: uuid.UUID,
    payload: LoadWorkspaceDraftUpdate,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    _auth=Depends(require_pilot_capability("loads.records", "update")),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftOut:
    row = await draft_service.update_workspace_draft(
        db,
        tenant_id,
        draft_id,
        payload,
        updated_by_platform_user_id=_platform_user_id(user),
    )
    return LoadWorkspaceDraftOut.model_validate(row)
