from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.driver import Driver
from app.models.driver_document import DriverDocument
from app.schemas.driver_document import DriverDocumentCreate, DriverDocumentOut

router = APIRouter(prefix="/driver-documents", tags=["Driver Documents"])


@router.get("/{driver_id}", response_model=list[DriverDocumentOut])
async def list_driver_documents(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DriverDocument)
        .where(DriverDocument.driver_id == driver_id)
        .order_by(DriverDocument.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{driver_id}", response_model=DriverDocumentOut, status_code=status.HTTP_201_CREATED)
async def create_driver_document(
    driver_id: int,
    payload: DriverDocumentCreate,
    db: AsyncSession = Depends(get_db),
):
    # Ensure driver exists
    exists = await db.execute(select(Driver.id).where(Driver.id == driver_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Driver not found")

    doc = DriverDocument(
        driver_id=driver_id,
        doc_type=payload.doc_type,
        title=payload.title,
        issue_date=payload.issue_date,
        expiry_date=payload.expiry_date,
        status=payload.status,
        notes=payload.notes,
        is_current=payload.is_current,
    )

    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc
