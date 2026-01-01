from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status

router = APIRouter(prefix="/api/v1", tags=["Auth"])


@router.get("/me")
async def get_me(
    request: Request,
    x_tenant_roles: str | None = Header(None),
    x_user_id: str | None = Header(None),
) -> dict:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context missing")

    roles = [r.strip().upper() for r in (x_tenant_roles or "").split(",") if r.strip()]
    user_id: int | None = None
    if x_user_id:
        try:
            user_id = int(x_user_id)
        except ValueError:
            user_id = None

    return {"user_id": user_id, "tenant_id": tenant_id, "roles": roles}
