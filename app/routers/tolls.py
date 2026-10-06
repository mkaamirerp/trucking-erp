"""Toll FILE/CSV intake and FILE import history (unmapped rows; not canonical transactions)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.schemas.toll import (
    TollCsvIntakeOut,
    TollFileBatchDetailOut,
    TollFileBatchListItemOut,
    TollManualStageIn,
    TollManualStageOut,
    TollManualValidateOut,
    TollPdfIntakeOut,
    TollPdfReviewDetailOut,
    TollPdfReviewListItemOut,
)
from app.services.toll_csv_intake import TollCsvIntakeError, persist_toll_csv_file, read_toll_csv_upload_bounded
from app.services.toll_file_history import (
    FILE_DETAIL_DEFAULT_LIMIT,
    FILE_DETAIL_MAX_LIMIT,
    TollFileHistoryError,
    get_toll_file_batch,
    list_toll_file_batches,
)
from app.services.toll_pdf_review import (
    PDF_REVIEW_DETAIL_DEFAULT_LIMIT,
    PDF_REVIEW_DETAIL_MAX_LIMIT,
    TollPdfReviewError,
    get_toll_pdf_review,
    list_toll_pdf_reviews,
    persist_toll_pdf_file,
)
from app.services.toll_manual_entry import (
    TollManualEntryError,
    create_manual_stage,
    discard_manual_stage,
    get_manual_stage,
    list_manual_stages,
    patch_manual_stage,
    stage_to_dict,
    validate_manual_stage,
)
from app.services.toll_wvpa_pdf import MAX_TOLL_PDF_BYTES, TollPdfIntakeError

router = APIRouter(
    prefix="/tolls",
    tags=["Tolls"],
    dependencies=[Depends(require_entitlement("admin_sensitive"))],
)


@router.post("/files/csv", response_model=TollCsvIntakeOut, status_code=status.HTTP_201_CREATED)
async def upload_toll_csv_file(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    filename = file.filename or "tolls.csv"
    created_by = str(user.user_id)
    try:
        body = await read_toll_csv_upload_bounded(file)
        result = await persist_toll_csv_file(
            db,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            filename=filename,
            body=body,
            content_type=file.content_type,
            created_by=created_by,
        )
    except TollCsvIntakeError as exc:
        detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    return TollCsvIntakeOut(**result.as_api_dict())


@router.get("/files", response_model=list[TollFileBatchListItemOut])
async def list_toll_csv_files(
    q: str | None = Query(None),
    _user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = _user
    items = await list_toll_file_batches(db, tenant_id=tenant_id, q=q)
    return [TollFileBatchListItemOut(**item) for item in items]


@router.get("/files/{batch_id}", response_model=TollFileBatchDetailOut)
async def get_toll_csv_file_batch(
    batch_id: int,
    row_offset: int = Query(0, ge=0),
    row_limit: int = Query(FILE_DETAIL_DEFAULT_LIMIT, ge=1, le=FILE_DETAIL_MAX_LIMIT),
    _user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = _user
    try:
        item = await get_toll_file_batch(
            db,
            tenant_id=tenant_id,
            batch_id=batch_id,
            row_offset=row_offset,
            row_limit=row_limit,
        )
    except TollFileHistoryError as exc:
        detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    return TollFileBatchDetailOut(**item)


@router.post("/files/pdf", response_model=TollPdfIntakeOut, status_code=status.HTTP_201_CREATED)
async def upload_toll_pdf_file(
    file: UploadFile = File(...),
    profile_code: str | None = Form(None),
    user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    filename = file.filename or "tolls.pdf"
    created_by = str(user.user_id)
    try:
        body = await read_toll_csv_upload_bounded(file, max_bytes=MAX_TOLL_PDF_BYTES)
        result = await persist_toll_pdf_file(
            db,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            filename=filename,
            body=body,
            content_type=file.content_type,
            created_by=created_by,
            profile_code=profile_code or "",
        )
    except TollPdfIntakeError as exc:
        detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    return TollPdfIntakeOut(**result.as_api_dict())


@router.get("/pdf-reviews", response_model=list[TollPdfReviewListItemOut])
async def list_toll_pdf_review_batches(
    q: str | None = Query(None),
    _user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = _user
    items = await list_toll_pdf_reviews(db, tenant_id=tenant_id, q=q)
    return [TollPdfReviewListItemOut(**item) for item in items]


@router.get("/pdf-reviews/{batch_id}", response_model=TollPdfReviewDetailOut)
async def get_toll_pdf_review_batch(
    batch_id: int,
    row_offset: int = Query(0, ge=0),
    row_limit: int = Query(PDF_REVIEW_DETAIL_DEFAULT_LIMIT, ge=1, le=PDF_REVIEW_DETAIL_MAX_LIMIT),
    _user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = _user
    try:
        item = await get_toll_pdf_review(
            db,
            tenant_id=tenant_id,
            batch_id=batch_id,
            row_offset=row_offset,
            row_limit=row_limit,
        )
    except TollPdfReviewError as exc:
        detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    return TollPdfReviewDetailOut(**item)


def _manual_http(exc: TollManualEntryError) -> HTTPException:
    return HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": exc.message},
    )


@router.post("/manual-entry/stages", response_model=TollManualStageOut, status_code=status.HTTP_201_CREATED)
async def create_toll_manual_stage(
    payload: TollManualStageIn | None = None,
    user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    created_by = str(user.user_id)
    try:
        stage = await create_manual_stage(
            db,
            tenant_id=tenant_id,
            created_by=created_by,
            payload=payload.model_dump(exclude_unset=True) if payload else None,
        )
    except TollManualEntryError as exc:
        raise _manual_http(exc) from exc
    return TollManualStageOut(**stage_to_dict(stage))


@router.get("/manual-entry/stages", response_model=list[TollManualStageOut])
async def list_toll_manual_stages(
    _user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = _user
    stages = await list_manual_stages(db, tenant_id=tenant_id)
    return [TollManualStageOut(**stage_to_dict(stage)) for stage in stages]


@router.get("/manual-entry/stages/{stage_id}", response_model=TollManualStageOut)
async def get_toll_manual_stage(
    stage_id: int,
    _user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = _user
    try:
        stage = await get_manual_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    except TollManualEntryError as exc:
        raise _manual_http(exc) from exc
    return TollManualStageOut(**stage_to_dict(stage))


@router.patch("/manual-entry/stages/{stage_id}", response_model=TollManualStageOut)
async def patch_toll_manual_stage(
    stage_id: int,
    payload: TollManualStageIn,
    user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    try:
        stage = await patch_manual_stage(
            db,
            tenant_id=tenant_id,
            stage_id=stage_id,
            patch=payload.model_dump(exclude_unset=True),
            updated_by=str(user.user_id),
        )
    except TollManualEntryError as exc:
        raise _manual_http(exc) from exc
    return TollManualStageOut(**stage_to_dict(stage))


@router.post("/manual-entry/stages/{stage_id}/validate", response_model=TollManualValidateOut)
async def validate_toll_manual_stage(
    stage_id: int,
    user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    try:
        stage, errors = await validate_manual_stage(
            db,
            tenant_id=tenant_id,
            stage_id=stage_id,
            updated_by=str(user.user_id),
        )
    except TollManualEntryError as exc:
        raise _manual_http(exc) from exc
    return TollManualValidateOut(ok=not errors, errors=errors, stage=TollManualStageOut(**stage_to_dict(stage)))


@router.post("/manual-entry/stages/{stage_id}/discard")
async def discard_toll_manual_stage(
    stage_id: int,
    _user: CurrentUser = Depends(get_current_user),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = _user
    try:
        await discard_manual_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    except TollManualEntryError as exc:
        raise _manual_http(exc) from exc
    return {"ok": True}
