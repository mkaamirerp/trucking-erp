"""Structured QR-derived payloads from broker/email documents (intake matching, not OCR-only)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Intake-only provenance: where the QR was decoded from (not a generic bucket).
EXTRACTED_FROM_SOURCE_TYPES = frozenset({"pdf", "image_attachment", "email_body_image", "other"})


class EmailIntakeQrExtraction(Base):
    """
    One row per decoded QR from email intake (e.g. rate con). Multiple distinct QRs per
    attachment/message = multiple rows. Same tenant+attachment+raw_payload is deduped by DB.

    Scope: intake / email / load-context metadata only — not general-purpose QR storage.
    """

    __tablename__ = "email_intake_qr_extractions"
    __table_args__ = (
        Index("ix_email_intake_qr_extractions_tenant_id", "tenant_id"),
        Index("ix_email_intake_qr_extractions_thread_id", "thread_id"),
        Index("ix_email_intake_qr_extractions_message_id", "message_id"),
        Index("ix_email_intake_qr_extractions_tenant_attachment", "tenant_id", "attachment_id"),
        Index("ix_email_intake_qr_extractions_tenant_raw_value", "tenant_id", "raw_value"),
        Index(
            "ix_email_intake_qr_extractions_tenant_normalized_value",
            "tenant_id",
            "normalized_value",
            postgresql_where=text("normalized_value IS NOT NULL"),
        ),
        # Dedup: same attachment re-processed must not insert identical raw_value twice.
        Index(
            "uq_email_intake_qr_tenant_attachment_raw",
            "tenant_id",
            "attachment_id",
            "raw_value",
            unique=True,
            postgresql_where=text("attachment_id IS NOT NULL"),
        ),
        # Attachment-less extractions: dedupe per message + raw payload.
        Index(
            "uq_email_intake_qr_tenant_message_raw",
            "tenant_id",
            "message_id",
            "raw_value",
            unique=True,
            postgresql_where=text("attachment_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)

    thread_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False)
    attachment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("email_message_attachments.id", ondelete="SET NULL"), nullable=True
    )

    #: Exact decoded QR payload; never overwritten — audit truth.
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    #: Optional normalized match key (trim, lowercase URL, etc.); use for lookups when set.
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: pdf | image_attachment | email_body_image | other
    extracted_from_source_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="other")
    #: 1-based page when source is PDF; NULL for non-PDF or unknown.
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    format_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decoder_backend: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ok")
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Filled when known at extraction time; often NULL until classification / human verification.
    linked_broker_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("brokers.id", ondelete="SET NULL"), nullable=True)
    #: Filled when a load is created or linked; may be set in a later intake step.
    linked_load_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("loads.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    thread = relationship("EmailThread", backref="intake_qr_extractions")
    message = relationship("EmailMessage", backref="intake_qr_extractions")
    attachment = relationship("EmailMessageAttachment", backref="intake_qr_extractions")
