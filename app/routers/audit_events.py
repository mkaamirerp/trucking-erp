from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.tenant import AuditEvent
from app.schemas.audit_events import AuditEventOut

router = APIRouter(prefix="/audit-events", tags=["audit-events"])


@router.get("/by-entity", response_model=list[AuditEventOut])
async def list_audit_events_by_entity(
    entity_type: str,
    entity_id: str,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    cap = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
        )
        .order_by(AuditEvent.event_at.desc(), AuditEvent.id.desc())
        .offset(off)
        .limit(cap)
    )
    rows = list((await db.scalars(stmt)).all())
    return [
        AuditEventOut(
            id=int(r.id),
            event_at=r.event_at,
            actor_user_id=int(r.actor_user_id) if r.actor_user_id is not None else None,
            actor_label=r.actor_label,
            module=r.module,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            entity_label=r.entity_label,
            action=r.action,
            request_id=r.request_id,
            correlation_id=r.correlation_id,
            source=r.source,
            visibility=r.visibility,
            changed_fields=r.changed_fields if isinstance(r.changed_fields, dict) else {},
        )
        for r in rows
    ]

