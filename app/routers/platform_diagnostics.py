"""Platform control-plane diagnostics (platform DB). Requires X-Platform-Admin-Key."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.platform import PlatformLoginFailureEvent
from app.routers.platform_tenants import require_platform_admin_key

router = APIRouter(prefix="/api/v1/platform", tags=["platform-diagnostics"])
logger = logging.getLogger(__name__)

_MAX_LIMIT = 500


@router.get("/login-failures")
async def list_login_failures(
    tenant_id: int | None = Query(default=None),
    reason: str | None = Query(default=None, alias="reason"),
    email_fingerprint: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=_MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    """Recent rows from platform_login_failure_events for operator support."""
    q = select(PlatformLoginFailureEvent)
    if tenant_id is not None:
        q = q.where(PlatformLoginFailureEvent.tenant_id == tenant_id)
    if reason:
        q = q.where(PlatformLoginFailureEvent.reason_code == reason.strip())
    if email_fingerprint:
        fp = email_fingerprint.strip().lower()
        q = q.where(PlatformLoginFailureEvent.email_fingerprint == fp)
    q = q.order_by(desc(PlatformLoginFailureEvent.created_at)).limit(limit)
    try:
        rows = (await db.execute(q)).scalars().all()
    except Exception as exc:
        logger.exception("platform_diagnostics.login_failures_list_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list login failures",
        ) from exc
    return [
        {
            "id": int(r.id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "tenant_id": int(r.tenant_id),
            "tenant_slug": r.tenant_slug,
            "tenant_auth_mode": r.tenant_auth_mode,
            "reason_code": r.reason_code,
            "email_fingerprint": r.email_fingerprint,
            "request_id": r.request_id,
            "request_host": r.request_host,
        }
        for r in rows
    ]
