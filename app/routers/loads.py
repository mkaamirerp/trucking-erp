from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.enforce import require_pilot_capability
from app.core.storage import download_response
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.schemas.load import (
    LoadCancelBody,
    LoadCreate,
    LoadMutationConcurrencyBody,
    LoadNoteCreate,
    LoadNoteOut,
    LoadResponse,
    LoadUpdate,
)
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.schemas.custody import LoadCustodyEventListResponse, LoadCustodySnapshotResponse
from app.services import future_movement_plans as fmp_service
from app.services import loads as loads_service
from app.services import trips as trips_service
from app.services import load_custody as custody_service
from app.schemas.load_pod_evidence import LoadPodEvidenceListResponse, LoadPodEvidenceOut
from app.services.load_document_parse_orchestrator import parse_load_workspace_document_orchestrated
from app.services.load_parser_pdf_safety import UnsafeLoadPdfError
from app.services.load_parser_duplicate_precheck import DuplicatePrecheckUnavailable
from app.services.load_pod_evidence import (
    PodEvidenceError,
    assert_pod_storage_key_tenant,
    get_load_pod_evidence_row,
    list_load_pod_evidence,
    upload_load_pod_evidence,
    LOAD_POD_MODULE,
)

router = APIRouter(prefix="/loads", tags=["loads"])


def _load_audit_actor(user: CurrentUser) -> tuple[int | None, str | None]:
    """Tenant audit_events.actor_user_id is tenant-scoped int — not platform UUID."""
    actor_user_id = int(user.tenant_user.id) if user.tenant_user else None
    return actor_user_id, _signed_in_actor_label(user)


def _signed_in_actor_label(user: CurrentUser) -> str | None:
    """Name of the logged-in account, for audit display. Email is not stored."""
    tu = user.tenant_user
    platform = user.user
    first = ((tu.first_name if tu is not None else None) or platform.first_name or "").strip()
    last = ((tu.last_name if tu is not None else None) or platform.last_name or "").strip()
    name = " ".join(part for part in (first, last) if part)
    if not name:
        return None
    return name[:128]


def _pod_actor(user: CurrentUser) -> tuple[int | None, str | None]:
    return _load_audit_actor(user)


@router.post("", response_model=LoadResponse, status_code=status.HTTP_201_CREATED)
async def create_load(
    payload: LoadCreate,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(require_pilot_capability("loads.records", "create")),
    db: AsyncSession = Depends(get_tenant_db),
):
    actor_user_id, _ = _load_audit_actor(user)
    load = await loads_service.create_load(
        db,
        tenant_id,
        payload,
        actor_user_id=actor_user_id,
        request_id=getattr(request.state, "request_id", None),
        source="ui",
    )
    return LoadResponse.model_validate(load)


@router.get("", response_model=dict)
async def list_loads(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(require_pilot_capability("loads.records", "view")),
    db: AsyncSession = Depends(get_tenant_db),
    status: Optional[List[str]] = Query(None),
    driver_id: int | None = Query(None),
    broker_id: int | None = Query(None),
    truck_id: int | None = Query(None),
    trailer_id: int | None = Query(None),
    search: str | None = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    dispatch_unassigned: bool = Query(False),
):
    if dispatch_unassigned:
        paged = await loads_service.list_dispatch_unassigned_loads(
            db,
            tenant_id=tenant_id,
            page=page,
            size=size,
        )
    else:
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
    items = await loads_service.enrich_load_responses(db, tenant_id, items)
    items = await loads_service.attach_cancel_audit(db, tenant_id, items)
    return {**paged, "items": items}


_MAX_PARSE_PDF_BYTES = 20 * 1024 * 1024


@router.post("/parse-document", response_model=LoadDocumentParseResponse)
async def parse_load_workspace_document(
    file: UploadFile = File(...),
    email_thread_id: int | None = Form(None),
    load_id: int | None = Form(None),
    continue_anyway: bool = Form(False),
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    Extract normalized load fields from an uploaded PDF for workspace hydration only.
    Does not create or update a load row. Optional thread/load ids are echo-only context.

    Uses the Rate Confirmation v2 product parser (acquisition + clean OpenAI handoff +
    mechanical validation); no PRODUCT_PARSE_DIAGNOSTICS fallback.
    """
    data = await file.read(_MAX_PARSE_PDF_BYTES + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > _MAX_PARSE_PDF_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF too large")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected a PDF file")
    try:
        return await parse_load_workspace_document_orchestrated(
            data,
            filename=file.filename or "upload.pdf",
            email_thread_id=email_thread_id,
            load_id=load_id,
            openai_chat_json_schema=None,
            tenant_id=tenant_id,
            db=db,
            continue_anyway=continue_anyway,
        )
    except UnsafeLoadPdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DuplicatePrecheckUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Duplicate check unavailable; AI parsing was not started.",
        ) from exc


@router.get("/{load_id}", response_model=LoadResponse)
async def get_load_detail(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(require_pilot_capability("loads.records", "view")),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    resp = LoadResponse.model_validate(load)
    enriched = await loads_service.enrich_load_responses(db, tenant_id, [resp])
    resp = enriched[0]
    verification_text = await loads_service.get_load_verification_extracted_text(db, tenant_id, load_id)
    if verification_text:
        resp = resp.model_copy(update={"verification_extracted_text": verification_text})
    enriched_cancel = await loads_service.attach_cancel_audit(db, tenant_id, [resp])
    resp = enriched_cancel[0]
    override_keys = await loads_service.get_load_parse_manual_override_keys(db, tenant_id, load)
    if override_keys:
        resp = resp.model_copy(update={"parse_manual_override_keys": override_keys})
    return resp


@router.patch("/{load_id}", response_model=LoadResponse)
async def update_load(
    load_id: int,
    payload: LoadUpdate,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(require_pilot_capability("loads.records", "update")),
    db: AsyncSession = Depends(get_tenant_db),
):
    actor_user_id, _ = _load_audit_actor(user)
    load = await loads_service.update_load(
        db,
        tenant_id,
        load_id,
        payload,
        actor_user_id=actor_user_id,
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
        request_id=getattr(request.state, "request_id", None),
        source="ui",
    )
    return LoadResponse.model_validate(load)


@router.post("/{load_id}/mark-ready", response_model=LoadResponse)
async def mark_load_ready(
    load_id: int,
    body: LoadMutationConcurrencyBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    actor_user_id, _ = _load_audit_actor(user)
    load = await loads_service.mark_load_ready(
        db,
        tenant_id,
        load_id,
        expected_concurrency_version=body.expected_concurrency_version,
        actor_user_id=actor_user_id,
        request_id=getattr(request.state, "request_id", None),
        source="ui",
    )
    resp = LoadResponse.model_validate(load)
    planned = await trips_service.get_open_planned_trip_for_load(db, tenant_id, load_id)
    updates: dict = {}
    if planned is not None:
        updates["open_planned_trip_id"] = planned[0]
        updates["open_planned_trip_number"] = planned[1]
    fmp_id = await fmp_service.get_open_future_movement_plan_id(db, tenant_id, load_id)
    if fmp_id is not None:
        updates["open_future_movement_plan_id"] = fmp_id
    if updates:
        resp = resp.model_copy(update=updates)
    return resp


@router.post("/{load_id}/cancel", response_model=LoadResponse)
async def cancel_load(
    load_id: int,
    body: LoadCancelBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Commercial cancel — preserves load row and history; closes OPEN TripLoads (Issue I5)."""
    actor_user_id, actor_label = _load_audit_actor(user)
    load = await loads_service.cancel_load(
        db,
        tenant_id,
        load_id,
        expected_concurrency_version=body.expected_concurrency_version,
        reason=body.reason,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        request_id=getattr(request.state, "request_id", None),
        source="ui",
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


@router.post("/{load_id}/pod", response_model=LoadPodEvidenceOut, status_code=status.HTTP_201_CREATED)
async def upload_load_pod(
    load_id: int,
    request: Request,
    file: UploadFile = File(...),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadPodEvidenceOut:
    actor_user_id, actor_label = _pod_actor(user)
    try:
        row = await upload_load_pod_evidence(
            db,
            tenant_id,
            tenant_slug,
            load_id,
            file,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            request_id=getattr(request.state, "request_id", None),
            source="ui",
        )
    except PodEvidenceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"detail": exc.message, "code": exc.code},
        ) from exc
    return LoadPodEvidenceOut.model_validate(row)


@router.get("/{load_id}/pod", response_model=LoadPodEvidenceListResponse)
async def list_load_pod(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> LoadPodEvidenceListResponse:
    rows = await list_load_pod_evidence(db, tenant_id, load_id)
    return LoadPodEvidenceListResponse(items=[LoadPodEvidenceOut.model_validate(r) for r in rows])


@router.get("/{load_id}/pod/{pod_id}/file")
async def download_load_pod_file(
    load_id: int,
    pod_id: int,
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    row = await get_load_pod_evidence_row(db, tenant_id, load_id, pod_id)
    assert_pod_storage_key_tenant(row, tenant_slug)
    return download_response(
        row.storage_key,
        module=LOAD_POD_MODULE,
        tenant_slug=tenant_slug,
        content_type=row.content_type or "application/octet-stream",
        filename=row.original_filename or f"pod-{pod_id}",
    )


@router.get("/{load_id}/rate-confirmation-pdf")
async def download_load_rate_confirmation_pdf(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    row, body = await loads_service.read_load_rate_confirmation_pdf_bytes(
        db, tenant_id, load_id, tenant_slug=tenant_slug
    )
    fname = row.filename or "rate-confirmation.pdf"
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
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
