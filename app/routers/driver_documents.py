from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.driver import Driver
from app.models.driver_document import DriverDocument
from app.schemas.driver_document import DriverDocumentCreate, DriverDocumentOut

router = APIRouter(prefix="/driver-documents", tags=["Driver Documents"])

# Doc types where only ONE can be current per driver
SINGLE_CURRENT_TYPES = {"CDL", "PASSPORT", "FAST", "ABSTRACT", "MEDICAL", "TWIC"}


def _is_valid_today(issue_date: date | None, expiry_date: date | None) -> bool:
    today = date.today()
    if issue_date is not None and issue_date > today:
        return False
    if expiry_date is not None and expiry_date < today:
        return False
    return True


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

    doc_type = payload.doc_type.upper().strip()

    # Backend decides is_current for single-current doc types
    should_be_current = (doc_type in SINGLE_CURRENT_TYPES) and _is_valid_today(
        payload.issue_date, payload.expiry_date
    )

    # IMPORTANT: do not start a nested transaction here (get_db may already have one)
    if should_be_current:
        await db.execute(
            update(DriverDocument)
            .where(
                DriverDocument.driver_id == driver_id,
                DriverDocument.doc_type == doc_type,
                DriverDocument.is_current.is_(True),
            )
            .values(is_current=False)
        )

    doc = DriverDocument(
        driver_id=driver_id,
        doc_type=doc_type,
        title=payload.title,
        issue_date=payload.issue_date,
        expiry_date=payload.expiry_date,
        status=payload.status,
        notes=payload.notes,
        # do not trust client-sent is_current for single-current types
        is_current=should_be_current if doc_type in SINGLE_CURRENT_TYPES else (payload.is_current or False),
    )

    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc
