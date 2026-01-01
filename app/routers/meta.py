from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/meta", tags=["Meta"])


@router.get("/roles")
async def list_roles():
    return ["DRIVER", "DISPATCHER", "MANAGER", "SAFETY", "ACCOUNTING", "MECHANIC", "OWNER", "HR"]
