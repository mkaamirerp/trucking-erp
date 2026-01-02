from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import save_driver_doc_upload_local
from app.models.driver_document import DriverDocument
from app.models.driver_document_file import DriverDocumentFile
from app.schemas.driver_documents import (
    DriverDocumentCreate,
    DriverDocumentCreatePath,
    DriverDocumentOut,
    DriverDocumentFileOut,
)
from app.deps.tenant import require_tenant

router = APIRouter(tags=["Driver Documents"])


@router.post("/driver-documents", response_model=DriverDocumentOut)
async def create_driver_document(
    payload: DriverDocumentCreate,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Enforce single current CDL/DRIVER_LICENSE per driver
    if payload.doc_type in {"CDL", "DRIVER_LICENSE"} and payload.is_current:
        await db.execute(
            update(DriverDocument)
            .where(
                DriverDocument.driver_id == payload.driver_id,
                DriverDocument.tenant_id == tenant_id,
                DriverDocument.doc_type == payload.doc_type,
                DriverDocument.is_current.is_(True),
            )
            .values(is_current=False)
        )

    doc = DriverDocument(**payload.model_dump(), tenant_id=tenant_id)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.post("/driver-documents/{driver_id}", response_model=DriverDocumentOut)
async def create_driver_document_for_driver(
    driver_id: int,
    payload: DriverDocumentCreatePath,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Enforce single current CDL/DRIVER_LICENSE per driver
    if payload.doc_type in {"CDL", "DRIVER_LICENSE"} and payload.is_current:
        await db.execute(
            update(DriverDocument)
            .where(
                DriverDocument.driver_id == driver_id,
                DriverDocument.tenant_id == tenant_id,
                DriverDocument.doc_type == payload.doc_type,
                DriverDocument.is_current.is_(True),
            )
            .values(is_current=False)
        )

    doc = DriverDocument(**payload.model_dump(), driver_id=driver_id, tenant_id=tenant_id)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def _list_docs_for_driver(
    db: AsyncSession, tenant_id: int, driver_id: int, include_inactive: bool
) -> list[DriverDocument]:
    q = select(DriverDocument).where(DriverDocument.driver_id == driver_id, DriverDocument.tenant_id == tenant_id)
    if not include_inactive:
        q = q.where(DriverDocument.is_active.is_(True))
    res = await db.execute(q.order_by(DriverDocument.id.desc()))
    return list(res.scalars().all())


@router.get("/driver-documents", response_model=list[DriverDocumentOut])
async def list_driver_documents(
    tenant_id: int = Depends(require_tenant),
    driver_id: int | None = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    if driver_id is None:
        raise HTTPException(status_code=404, detail="Driver id is required")
    return await _list_docs_for_driver(db, tenant_id, driver_id, include_inactive)


@router.get("/driver-documents/{driver_id}", response_model=list[DriverDocumentOut])
async def list_driver_documents_by_path(
    driver_id: int,
    tenant_id: int = Depends(require_tenant),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    return await _list_docs_for_driver(db, tenant_id, driver_id, include_inactive)


@router.post("/driver-documents/{document_id}/deactivate", response_model=DriverDocumentOut)
async def deactivate_driver_document(
    document_id: int,
    tenant_id: int = Depends(require_tenant),
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(DriverDocument).where(DriverDocument.id == document_id, DriverDocument.tenant_id == tenant_id)
    )
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Driver document not found")

    if not doc.is_active:
        return doc

    doc.is_active = False
    doc.deactivated_at = datetime.utcnow()
    doc.deactivated_reason = reason
    await db.commit()
    await db.refresh(doc)
    return doc



@router.post("/driver-documents/{document_id}/files", response_model=DriverDocumentFileOut)
async def upload_driver_document_file(
    document_id: int,
    tenant_id: int = Depends(require_tenant),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(DriverDocument).where(DriverDocument.id == document_id, DriverDocument.tenant_id == tenant_id)
    )
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Driver document not found")
    if not doc.is_active:
        raise HTTPException(status_code=400, detail="Driver document is inactive")

    stored = await save_driver_doc_upload_local(file)

    doc_file = DriverDocumentFile(
        driver_document_id=document_id,
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        content_type=stored.content_type,
        file_size_bytes=stored.file_size_bytes,
        sha256=stored.sha256,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(doc_file)
    await db.commit()
    await db.refresh(doc_file)
    return doc_file



@router.get("/driver-documents/{document_id}/files", response_model=list[DriverDocumentFileOut])
async def list_driver_document_files(
    document_id: int,
    tenant_id: int = Depends(require_tenant),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    # Ensure document belongs to tenant
    doc = await db.scalar(
        select(DriverDocument).where(DriverDocument.id == document_id, DriverDocument.tenant_id == tenant_id)
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Driver document not found")
    q = select(DriverDocumentFile).where(
        DriverDocumentFile.driver_document_id == document_id,
        DriverDocumentFile.tenant_id == tenant_id,
    )
    if not include_inactive:
        q = q.where(DriverDocumentFile.is_active.is_(True))
    res = await db.execute(q.order_by(DriverDocumentFile.id.desc()))
    return list(res.scalars().all())


@router.post("/driver-documents/{document_id}/files/{file_id}/deactivate", response_model=DriverDocumentFileOut)
async def deactivate_driver_document_file(
    document_id: int,
    file_id: int,
    tenant_id: int = Depends(require_tenant),
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    res_doc = await db.execute(
        select(DriverDocument).where(DriverDocument.id == document_id, DriverDocument.tenant_id == tenant_id)
    )
    doc = res_doc.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Driver document not found")

    res = await db.execute(
        select(DriverDocumentFile).where(
            DriverDocumentFile.id == file_id,
            DriverDocumentFile.driver_document_id == document_id,
            DriverDocumentFile.tenant_id == tenant_id,
        )
    )
    doc_file = res.scalar_one_or_none()
    if not doc_file:
        raise HTTPException(status_code=404, detail="Driver document file not found")

    if not doc_file.is_active:
        return doc_file

    doc_file.is_active = False
    doc_file.deactivated_at = datetime.utcnow()
    doc_file.deactivated_reason = reason
    await db.commit()
    await db.refresh(doc_file)
    return doc_file
