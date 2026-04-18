"""Tenant-wide append-only audit events (tenant DB).

This is the canonical audit foundation table. All modules should write audit via
`app.services.audit_events.write_audit_event` (not via bespoke per-router formats).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    module: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_label: Mapped[str | None] = mapped_column(String(256), nullable=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    subaction: Mapped[str | None] = mapped_column(String(64), nullable=True)

    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, server_default="normal")

    changed_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    snapshot_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    snapshot_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    legacy_tenant_audit_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

