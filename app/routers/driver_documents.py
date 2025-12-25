from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.storage import save_driver_doc_upload_local
from app.models.driver_document import DriverDocument
from app.models.driver_document_file import DriverDocumentFile
from app.schemas.driver_documents import (
    DriverDocumentCreate,
    DriverDocumentOut,
    DriverDocumentFileOut,
)

router = APIRouter(tags=["Driver Documents"])


@router.post("/driver-documents", response_model=DriverDocumentOut)
async def create_driver_document(payload: DriverDocumentCreate, db: AsyncSession = Depends(get_db)):
    doc = DriverDocument(**payload.model_dump())
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/driver-documents", response_model=list[DriverDocumentOut])
async def list_driver_documents(
    driver_id: int = Query(...)
    ,include_inactive: bool = Query(False)
    ,db: AsyncSession = Depends(get_db),
):
    q = select(DriverDocument).where(DriverDocument.driver_id == driver_id)
    if not include_inactive:
        q = q.where(DriverDocument.is_active.is_(True))
    res = await db.execute(q.order_by(DriverDocument.id.desc()))
    return list(res.scalars().all())


@router.post("/driver-documents/{document_id}/deactivate", response_model=DriverDocumentOut)
async def deactivate_driver_document(
    document_id: int,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DriverDocument).where(DriverDocument.id == document_id))
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
    file: UploadFile = File(...)
    ,db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(DriverDocument).where(DriverDocument.id == document_id))
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
    )
    db.add(doc_file)
    await db.commit()
    await db.refresh(doc_file)
    return doc_file



@router.get("/driver-documents/{document_id}/files", response_model=list[DriverDocumentFileOut])
async def list_driver_document_files(
    document_id: int,
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    q = select(DriverDocumentFile).where(DriverDocumentFile.driver_document_id == document_id)
    if not include_inactive:
        q = q.where(DriverDocumentFile.is_active.is_(True))
    res = await db.execute(q.order_by(DriverDocumentFile.id.desc()))
    return list(res.scalars().all())


@router.post("/driver-documents/{document_id}/files/{file_id}/deactivate", response_model=DriverDocumentFileOut)
async def deactivate_driver_document_file(
    document_id: int,
    file_id: int,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    res_doc = await db.execute(select(DriverDocument).where(DriverDocument.id == document_id))
    doc = res_doc.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Driver document not found")

    res = await db.execute(
        select(DriverDocumentFile).where(
            DriverDocumentFile.id == file_id,
            DriverDocumentFile.driver_document_id == document_id,
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
