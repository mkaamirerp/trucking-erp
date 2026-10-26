"""Load workspace drafts — commercial fields before Load promotion."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.enforce import require_pilot_capability
from app.core.storage import download_response
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.schemas.load_workspace_draft import (
    LoadWorkspaceDraftCreate,
    LoadWorkspaceDraftDiscard,
    LoadWorkspaceDraftListOut,
    LoadWorkspaceDraftOut,
    LoadWorkspaceDraftParseOut,
    LoadWorkspaceDraftPromote,
    LoadWorkspaceDraftPromoteOut,
    LoadWorkspaceDraftUpdate,
)
from app.services import load_workspace_draft as draft_service
from app.services.load_parser_duplicate_precheck import DuplicatePrecheckUnavailable
from app.services.load_workspace_draft_lifecycle import (
    discard_workspace_draft,
    get_workspace_draft_with_lifecycle,
)
from app.services.load_workspace_draft_document import (
    LOAD_WORKSPACE_DRAFT_PDF_MODULE,
    get_workspace_draft_pdf_row,
    parse_and_attach_workspace_draft_pdf,
)
from app.services.load_workspace_draft_promotion import promote_workspace_draft

router = APIRouter(prefix="/load-workspace-drafts", tags=["load-workspace-drafts"])


def _platform_user_id(user: CurrentUser) -> str:
    return str(user.user_id)


@router.post("", response_model=LoadWorkspaceDraftOut, status_code=status.HTTP_201_CREATED)
async def create_load_workspace_draft(
    payload: LoadWorkspaceDraftCreate,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftOut:
    row = await draft_service.create_workspace_draft(
        db,
        tenant_id,
        payload,
        created_by_platform_user_id=_platform_user_id(user),
    )
    return LoadWorkspaceDraftOut.model_validate(row)


@router.get("", response_model=LoadWorkspaceDraftListOut)
async def list_load_workspace_drafts(
    status: str = Query("draft", max_length=32),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftListOut:
    items, total = await draft_service.list_workspace_drafts(
        db, tenant_id, status=status, page=page, size=size
    )
    return LoadWorkspaceDraftListOut(
        items=[LoadWorkspaceDraftOut.model_validate(row) for row in items],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{draft_id}", response_model=LoadWorkspaceDraftOut)
async def get_load_workspace_draft(
    draft_id: uuid.UUID,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftOut:
    row = await get_workspace_draft_with_lifecycle(db, tenant_id, draft_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    return LoadWorkspaceDraftOut.model_validate(row)


@router.post("/{draft_id}/discard", response_model=LoadWorkspaceDraftOut)
async def discard_load_workspace_draft(
    draft_id: uuid.UUID,
    payload: LoadWorkspaceDraftDiscard,
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftOut:
    row = await discard_workspace_draft(
        db,
        tenant_id,
        tenant_slug,
        draft_id,
        discard_reason=payload.discard_reason,
        updated_by_platform_user_id=_platform_user_id(user),
    )
    return LoadWorkspaceDraftOut.model_validate(row)


@router.patch("/{draft_id}", response_model=LoadWorkspaceDraftOut)
async def update_load_workspace_draft(
    draft_id: uuid.UUID,
    payload: LoadWorkspaceDraftUpdate,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
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


@router.post("/{draft_id}/parse-document", response_model=LoadWorkspaceDraftParseOut)
async def parse_workspace_draft_document(
    draft_id: uuid.UUID,
    file: UploadFile = File(...),
    expected_concurrency_version: int | None = Form(None),
    continue_anyway: bool = Form(False),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftParseOut:
    """Parse a rate-confirmation PDF, persist file + accepted parse on the draft (no Load row)."""
    try:
        draft, parse = await parse_and_attach_workspace_draft_pdf(
            db,
            tenant_id,
            tenant_slug,
            draft_id,
            file,
            updated_by_platform_user_id=_platform_user_id(user),
            expected_concurrency_version=expected_concurrency_version,
            continue_anyway=continue_anyway,
        )
    except DuplicatePrecheckUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Duplicate check unavailable; AI parsing was not started.",
        ) from exc
    return LoadWorkspaceDraftParseOut(
        draft=LoadWorkspaceDraftOut.model_validate(draft),
        parse=parse,
    )


@router.get("/{draft_id}/rate-confirmation-pdf")
async def download_workspace_draft_rate_confirmation_pdf(
    draft_id: uuid.UUID,
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    row = await get_workspace_draft_pdf_row(db, tenant_id, draft_id)
    return download_response(
        row.pdf_storage_key,
        module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
        tenant_slug=tenant_slug,
        content_type="application/pdf",
        filename=row.pdf_filename or "rate-confirmation.pdf",
        disposition="inline",
    )


@router.post("/{draft_id}/promote", response_model=LoadWorkspaceDraftPromoteOut)
async def promote_load_workspace_draft(
    draft_id: uuid.UUID,
    payload: LoadWorkspaceDraftPromote,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(require_pilot_capability("loads.records", "create")),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadWorkspaceDraftPromoteOut:
    result = await promote_workspace_draft(
        db,
        tenant_id,
        draft_id,
        payload,
        promoted_by_platform_user_id=_platform_user_id(user),
    )
    return LoadWorkspaceDraftPromoteOut(
        draft=LoadWorkspaceDraftOut.model_validate(result.draft),
        load_id=result.load_id,
        trip_id=result.trip_id,
        idempotent_replay=result.idempotent_replay,
    )
