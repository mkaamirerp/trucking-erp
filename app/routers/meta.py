from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant

router = APIRouter(
    prefix="/api/v1/meta",
    tags=["Meta"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/roles")
async def list_roles(_: int = Depends(require_tenant)):
    return ["DRIVER", "DISPATCHER", "MANAGER", "SAFETY", "ACCOUNTING", "MECHANIC", "OWNER", "HR"]
