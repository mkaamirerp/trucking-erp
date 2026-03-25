from fastapi import Depends, HTTPException, status

from app.deps.auth import CurrentUser, get_current_user


async def require_tenant_admin(user: CurrentUser = Depends(get_current_user)) -> None:
    """Require TENANT_ADMIN from platform membership (DB), not client headers."""
    role = (user.role or "").strip().upper()
    if role != "TENANT_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "TENANT_ADMIN role required", "code": "RBAC_FORBIDDEN"},
        )
