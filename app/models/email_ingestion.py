"""Tenant-scoped inbound email foundations: threads and messages."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmailThread(Base):
    __tablename__ = "email_threads"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_thread_id",
            name="uq_email_threads_tenant_provider_external_thread_id",
        ),
        Index("ix_email_threads_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    external_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    participants_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    linked_load_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("loads.id", ondelete="SET NULL"), nullable=True)
    intake_bucket: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="needs_review", default="needs_review"
    )
    confidence_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    routing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_message_id",
            name="uq_email_messages_tenant_provider_external_message_id",
        ),
        Index("ix_email_messages_tenant_id", "tenant_id"),
        Index("ix_email_messages_thread_id", "thread_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thread_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    to_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    cc_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    bcc_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    extraction_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
