"""Toll FILE/CSV intake and FILE import history (unmapped rows; not canonical transactions)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.schemas.toll import TollCsvIntakeOut, TollFileBatchDetailOut, TollFileBatchListItemOut
from app.services.toll_csv_intake import TollCsvIntakeError, persist_toll_csv_file, read_toll_csv_upload_bounded
from app.services.toll_file_history import (
    FILE_DETAIL_DEFAULT_LIMIT,
    FILE_DETAIL_MAX_LIMIT,
    TollFileHistoryError,
    get_toll_file_batch,
    list_toll_file_batches,
)

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
