"""Tenant-scoped attachment metadata for synced email messages."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmailMessageAttachment(Base):
    __tablename__ = "email_message_attachments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "message_id",
            "external_attachment_id",
            name="uq_email_message_attachments_tenant_provider_message_attachment",
        ),
        Index("ix_email_message_attachments_tenant_id", "tenant_id"),
        Index("ix_email_message_attachments_message_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    external_attachment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_inline: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    download_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="metadata_only")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
