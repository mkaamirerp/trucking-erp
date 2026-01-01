from fastapi import Header, HTTPException, status


async def require_tenant_admin(x_tenant_roles: str | None = Header(None)) -> None:
    """
    Minimal RBAC gate: require TENANT_ADMIN in X-Tenant-Roles header.
    Accepts comma-separated roles; comparison is case-insensitive.
    """
    roles = {r.strip().upper() for r in (x_tenant_roles or "").split(",") if r.strip()}
    if "TENANT_ADMIN" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "TENANT_ADMIN role required", "code": "RBAC_FORBIDDEN"},
        )
