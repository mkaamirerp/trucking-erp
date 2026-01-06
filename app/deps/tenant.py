from fastapi import HTTPException, Request, status


def require_tenant(request: Request) -> int:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant context",
        )
    return int(tenant_id)
