from __future__ import annotations

from fastapi import APIRouter, Depends
from app.deps.tenant import require_tenant

router = APIRouter(prefix="/api/v1/meta", tags=["Meta"])


@router.get("/roles")
async def list_roles(_: int = Depends(require_tenant)):
    return ["DRIVER", "DISPATCHER", "MANAGER", "SAFETY", "ACCOUNTING", "MECHANIC", "OWNER", "HR"]
