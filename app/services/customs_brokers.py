"""Tenant-scoped customs broker and contact CRUD + search."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customs_broker import CustomsBroker, CustomsBrokerContact
from app.schemas.customs_broker import (
    CustomsBrokerContactCreate,
    CustomsBrokerContactUpdate,
    CustomsBrokerCreate,
    CustomsBrokerUpdate,
)
from app.utils.pagination import paginate


async def create_customs_broker(db: AsyncSession, tenant_id: int, payload: CustomsBrokerCreate) -> CustomsBroker:
    row = CustomsBroker(**payload.model_dump(), tenant_id=tenant_id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_customs_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> CustomsBroker | None:
    result = await db.execute(
        select(CustomsBroker).where(CustomsBroker.id == broker_id, CustomsBroker.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def list_customs_brokers(
    db: AsyncSession,
    tenant_id: int,
    *,
    include_inactive: bool = False,
    page: int = 1,
    size: int = 25,
):
    stmt = select(CustomsBroker).where(CustomsBroker.tenant_id == tenant_id)
    if not include_inactive:
        stmt = stmt.where(CustomsBroker.is_active.is_(True))
    stmt = stmt.order_by(CustomsBroker.id.desc())
    return await paginate(db, stmt, page=page, size=size)


async def search_customs_brokers(
    db: AsyncSession,
    tenant_id: int,
    q: str,
    *,
    page: int = 1,
    size: int = 25,
):
    term = (q or "").strip()
    if len(term) < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Search query required")
    pat = f"%{term}%"
    stmt = (
        select(CustomsBroker)
        .where(CustomsBroker.tenant_id == tenant_id, CustomsBroker.is_active.is_(True))
        .where(
            or_(
                CustomsBroker.legal_name.ilike(pat),
                CustomsBroker.phone_primary.ilike(pat),
                CustomsBroker.phone_secondary.ilike(pat),
                CustomsBroker.fax.ilike(pat),
                CustomsBroker.generic_email.ilike(pat),
            )
        )
        .order_by(CustomsBroker.legal_name.asc())
    )
    return await paginate(db, stmt, page=page, size=size)


async def update_customs_broker(
    db: AsyncSession, tenant_id: int, broker_id: int, payload: CustomsBrokerUpdate
) -> CustomsBroker:
    row = await get_customs_broker(db, tenant_id, broker_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customs broker not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def soft_delete_customs_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> None:
    row = await get_customs_broker(db, tenant_id, broker_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customs broker not found")
    row.is_active = False
    await db.commit()


# --- Contacts ---


async def list_contacts(
    db: AsyncSession, tenant_id: int, broker_id: int, *, include_inactive: bool = False
) -> list[CustomsBrokerContact]:
    broker = await get_customs_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customs broker not found")
    stmt = select(CustomsBrokerContact).where(
        CustomsBrokerContact.tenant_id == tenant_id,
        CustomsBrokerContact.customs_broker_id == broker_id,
    )
    if not include_inactive:
        stmt = stmt.where(CustomsBrokerContact.is_active.is_(True))
    stmt = stmt.order_by(CustomsBrokerContact.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_contact(db: AsyncSession, tenant_id: int, broker_id: int, contact_id: int) -> CustomsBrokerContact | None:
    result = await db.execute(
        select(CustomsBrokerContact).where(
            CustomsBrokerContact.id == contact_id,
            CustomsBrokerContact.tenant_id == tenant_id,
            CustomsBrokerContact.customs_broker_id == broker_id,
        )
    )
    return result.scalar_one_or_none()


async def create_contact(
    db: AsyncSession, tenant_id: int, broker_id: int, payload: CustomsBrokerContactCreate
) -> CustomsBrokerContact:
    if not await get_customs_broker(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customs broker not found")
    row = CustomsBrokerContact(
        **payload.model_dump(),
        tenant_id=tenant_id,
        customs_broker_id=broker_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_contact(
    db: AsyncSession, tenant_id: int, broker_id: int, contact_id: int, payload: CustomsBrokerContactUpdate
) -> CustomsBrokerContact:
    row = await get_contact(db, tenant_id, broker_id, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def soft_delete_contact(db: AsyncSession, tenant_id: int, broker_id: int, contact_id: int) -> None:
    row = await get_contact(db, tenant_id, broker_id, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    row.is_active = False
    await db.commit()
