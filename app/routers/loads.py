from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.load import (
    LoadCreate,
    LoadMutationConcurrencyBody,
    LoadNoteCreate,
    LoadNoteOut,
    LoadResponse,
    LoadUpdate,
)
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.schemas.custody import LoadCustodyEventListResponse, LoadCustodySnapshotResponse
from app.services import loads as loads_service
from app.services import load_custody as custody_service
from app.services.load_document_parse_orchestrator import parse_load_workspace_document_orchestrated

router = APIRouter(prefix="/loads", tags=["loads"])


@router.post("", response_model=LoadResponse, status_code=status.HTTP_201_CREATED)
async def create_load(
    payload: LoadCreate,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    # Slice 5: request/user captured for future audit correlation; create_load audit currently best-effort.
    _ = getattr(request.state, "request_id", None) if request else None
    _ = getattr(user, "user_id", None)
    load = await loads_service.create_load(db, tenant_id, payload)
    return LoadResponse.model_validate(load)


@router.get("", response_model=dict)
async def list_loads(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status: Optional[List[str]] = Query(None),
    driver_id: int | None = Query(None),
    broker_id: int | None = Query(None),
    truck_id: int | None = Query(None),
    trailer_id: int | None = Query(None),
    search: str | None = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await loads_service.list_loads(
        db,
        tenant_id=tenant_id,
        statuses=status,
        driver_id=driver_id,
        broker_id=broker_id,
        truck_id=truck_id,
        trailer_id=trailer_id,
        search=search,
        page=page,
        size=size,
    )
    items = [LoadResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


_MAX_PARSE_PDF_BYTES = 20 * 1024 * 1024


@router.post("/parse-document", response_model=LoadDocumentParseResponse)
async def parse_load_workspace_document(
    file: UploadFile = File(...),
    email_thread_id: int | None = Form(None),
    load_id: int | None = Form(None),
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Extract normalized load fields from an uploaded PDF for workspace hydration only.
    Does not create or update a load row. Optional thread/load ids are echo-only context.

    Uses the product guarded parser path only; no legacy parser fallback.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > _MAX_PARSE_PDF_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF too large")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected a PDF file")
    return await parse_load_workspace_document_orchestrated(
        data,
        filename=file.filename or "upload.pdf",
        email_thread_id=email_thread_id,
        load_id=load_id,
        openai_chat_json_schema=None,
        tenant_id=tenant_id,
        db=db,
    )


@router.get("/{load_id}", response_model=LoadResponse)
async def get_load_detail(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return LoadResponse.model_validate(load)


@router.patch("/{load_id}", response_model=LoadResponse)
async def update_load(
    load_id: int,
    payload: LoadUpdate,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.update_load(
        db,
        tenant_id,
        load_id,
        payload,
        actor_user_id=getattr(user, "user_id", None),
        request_id=getattr(request.state, "request_id", None),
        source="ui",
    )
    return LoadResponse.model_validate(load)


@router.post("/{load_id}/confirm-document-snapshot", response_model=LoadResponse)
async def confirm_document_snapshot(
    load_id: int,
    body: LoadMutationConcurrencyBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.confirm_load_customs_document_snapshot(
        db,
        tenant_id,
        load_id,
        confirming_user_id=getattr(user, "user_id", None),
        expected_concurrency_version=body.expected_concurrency_version,
    )
    return LoadResponse.model_validate(load)


@router.post("/{load_id}/mark-ready", response_model=LoadResponse)
async def mark_load_ready(
    load_id: int,
    body: LoadMutationConcurrencyBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.mark_load_ready(
        db, tenant_id, load_id, expected_concurrency_version=body.expected_concurrency_version
    )
    return LoadResponse.model_validate(load)


@router.get("/{load_id}/custody", response_model=LoadCustodySnapshotResponse)
async def get_load_custody(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadCustodySnapshotResponse:
    """Current custody snapshot for a Load (read-only)."""
    return await custody_service.get_load_custody_snapshot(db, tenant_id, load_id)


@router.get("/{load_id}/custody-events", response_model=LoadCustodyEventListResponse)
async def list_load_custody_events(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> LoadCustodyEventListResponse:
    """Append-only custody event history for a Load (read-only)."""
    return await custody_service.list_load_custody_events(
        db, tenant_id, load_id, limit=limit, offset=offset
    )


@router.get("/{load_id}/notes", response_model=list)
async def list_load_notes(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    notes = await loads_service.list_load_notes(db, tenant_id, load_id)
    return [LoadNoteOut.model_validate(n) for n in notes]


@router.post("/{load_id}/notes", response_model=LoadNoteOut, status_code=status.HTTP_201_CREATED)
async def add_load_note(
    load_id: int,
    payload: LoadNoteCreate,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    note = await loads_service.add_load_note(
        db,
        tenant_id,
        load_id,
        payload.body,
        author_user_id=getattr(user, "user_id", None),
        request_id=getattr(request.state, "request_id", None),
        source="ui",
    )
    return LoadNoteOut.model_validate(note)


@router.delete("/{load_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_load(
    load_id: int,
    expected_concurrency_version: int = Query(..., ge=1),
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await loads_service.delete_load(
        db, tenant_id, load_id, expected_concurrency_version=expected_concurrency_version
    )
    return {}
