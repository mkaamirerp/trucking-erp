from __future__ import annotations

from typing import Generic, Iterable, Type, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class TenantAwareRepository(Generic[T]):
    """Helper to enforce tenant scoping on reads by construction."""

    def __init__(self, model: Type[T], session: AsyncSession, tenant_id: int):
        self.model = model
        self.session = session
        self.tenant_id = tenant_id

    def base_query(self) -> Select:
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    async def get_by_id(self, object_id: int) -> T | None:
        return await self.session.scalar(self.base_query().where(self.model.id == object_id))

    async def list_all(self, extra_filters: Iterable | None = None) -> list[T]:
        stmt = self.base_query()
        for flt in extra_filters or []:
            stmt = stmt.where(flt)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
