from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.models.platform import PlatformTenant

logger = logging.getLogger(__name__)

# Allowed/ready values are case-insensitive.
ALLOWED_TENANT_STATUSES = {"ACTIVE", "READ_ONLY"}
ALLOWED_BILLING_STATUSES = {None, "OK", "ACTIVE"}


def _norm(value: str | None) -> str:
    return value.upper() if value else ""


def ensure_tenant_ready(tenant: PlatformTenant | None) -> PlatformTenant:
    """Validate that the platform tenant is usable for tenant-scoped routes."""
    if tenant is None or _norm(tenant.status) not in ALLOWED_TENANT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant inactive or not found",
        )

    if _norm(tenant.db_status) != "READY":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant DB not ready",
        )

    if tenant.provisioned_at is None:
        logger.warning("tenant_missing_provisioned_at tenant_id=%s slug=%s", tenant.id, tenant.slug)

    if tenant.billing_status is not None and _norm(tenant.billing_status) not in ALLOWED_BILLING_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant billing problem",
        )

    return tenant
