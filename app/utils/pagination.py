from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(db: AsyncSession, stmt: Select, page: int = 1, size: int = 25) -> dict[str, Any]:
    page = max(1, int(page or 1))
    size = max(1, min(int(size or 25), 200))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.limit(size).offset((page - 1) * size)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return {"items": items, "page": page, "size": size, "total": total}
