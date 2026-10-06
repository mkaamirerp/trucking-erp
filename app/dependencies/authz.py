from fastapi import Depends, HTTPException, status

from app.deps.admin import is_tenant_admin
from app.deps.auth import CurrentUser, get_current_user


async def require_tenant_admin(user: CurrentUser = Depends(get_current_user)) -> None:
    """Require a canonical tenant-admin role (see app.deps.admin.is_tenant_admin)."""
    if not is_tenant_admin(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "Tenant admin role required", "code": "RBAC_FORBIDDEN"},
        )
