from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker
from app.schemas.broker import BrokerCreate, BrokerUpdate
from app.utils.pagination import paginate


async def create_broker(db: AsyncSession, tenant_id: int, payload: BrokerCreate) -> Broker:
    broker = Broker(**payload.model_dump(), tenant_id=tenant_id)
    db.add(broker)
    await db.commit()
    await db.refresh(broker)
    return broker


async def get_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> Broker | None:
    result = await db.execute(select(Broker).where(Broker.id == broker_id, Broker.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def list_brokers(db: AsyncSession, tenant_id: int, page: int = 1, size: int = 25):
    stmt = select(Broker).where(Broker.tenant_id == tenant_id).order_by(Broker.id.desc())
    return await paginate(db, stmt, page=page, size=size)


async def update_broker(db: AsyncSession, tenant_id: int, broker_id: int, payload: BrokerUpdate) -> Broker:
    broker = await get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(broker, key, value)

    await db.commit()
    await db.refresh(broker)
    return broker


async def delete_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> None:
    broker = await get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")

    await db.delete(broker)
    await db.commit()
