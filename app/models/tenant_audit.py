"""
Tenant audit log model.

Lives in TENANT DB only.
Used for security, compliance, and admin forensics.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

from app.models.base import Base


class TenantAuditLog(Base):
    __tablename__ = "tenant_audit_logs"

    id = Column(Integer, primary_key=True)

    # Safety: redundant tenant_id even though DB is tenant-scoped
    tenant_id = Column(Integer, nullable=False)

    actor_user_id = Column(Integer, nullable=True)

    action = Column(String(64), nullable=False)
    object_type = Column(String(64), nullable=False)
    object_id = Column(String(128), nullable=True)

    details_json = Column(JSON, nullable=True)

    ip = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
