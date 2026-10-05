"""Toll FILE/CSV intake API (Segment 2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.schemas.toll import TollCsvIntakeOut
from app.services.toll_csv_intake import TollCsvIntakeError, persist_toll_csv_file

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
    body = await file.read()
    filename = file.filename or "tolls.csv"
    created_by = str(user.user_id)
    try:
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
