"""Tenant-scoped load workspace drafts (pre-promotion commercial workspace)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

LOAD_WORKSPACE_DRAFT_STATUSES = frozenset({"draft", "promoted", "discarded", "expired"})
LOAD_WORKSPACE_PDF_UPLOAD_STATES = frozenset({"idle", "uploading", "ready"})
LOAD_WORKSPACE_RETENTION_CLASSES = frozenset({"workspace_ttl", "commercial_permanent"})


class LoadWorkspaceDraft(Base):
    __tablename__ = "load_workspace_drafts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_load_workspace_drafts_tenant_id_id"),
        Index(
            "uq_load_workspace_drafts_tenant_promoted_load_id",
            "tenant_id",
            "promoted_load_id",
            unique=True,
            postgresql_where=text("promoted_load_id IS NOT NULL"),
        ),
        Index(
            "uq_load_workspace_drafts_tenant_promotion_idempotency_key",
            "tenant_id",
            "promotion_idempotency_key",
            unique=True,
            postgresql_where=text("promotion_idempotency_key IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["tenant_id", "promoted_load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_workspace_drafts_promoted_load_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "email_thread_id"],
            ["email_threads.tenant_id", "email_threads.id"],
            name="fk_load_workspace_drafts_email_thread_tenant",
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "status in ('draft', 'promoted', 'discarded', 'expired')",
            name="ck_load_workspace_drafts_status",
        ),
        CheckConstraint(
            "pdf_upload_state in ('idle', 'uploading', 'ready')",
            name="ck_load_workspace_drafts_pdf_upload_state",
        ),
        CheckConstraint(
            "pdf_retention_class in ('workspace_ttl', 'commercial_permanent')",
            name="ck_load_workspace_drafts_pdf_retention_class",
        ),
        CheckConstraint(
            "(status = 'promoted' AND promoted_load_id IS NOT NULL) "
            "OR (status != 'promoted' AND promoted_load_id IS NULL)",
            name="ck_load_workspace_drafts_promoted_load_id_status",
        ),
        Index("ix_load_workspace_drafts_tenant_status_expires", "tenant_id", "status", "expires_at"),
        Index(
            "ix_load_workspace_drafts_tenant_creator_updated",
            "tenant_id",
            "created_by_platform_user_id",
            text("updated_at DESC"),
        ),
        Index(
            "ix_load_workspace_drafts_tenant_email_thread",
            "tenant_id",
            "email_thread_id",
            postgresql_where=text("email_thread_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    draft_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    draft_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    source_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by_platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    email_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_retention_class: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="workspace_ttl"
    )
    pdf_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pdf_upload_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="idle")
    pdf_pending_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_upload_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pdf_upload_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_parse_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    accepted_parse_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_parse_pdf_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_load_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promotion_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
