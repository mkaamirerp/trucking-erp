"""Tenant-side email mailbox config. Metadata only; secrets in platform."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TenantEmailMailbox(Base):
    """Primary mailbox config per tenant. credential_ref links to platform encrypted secret."""
    __tablename__ = "tenant_email_mailboxes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    credential_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    mailbox_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="imap")
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    inbound_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    outbound_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    connection_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")
    provider_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imap_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    use_ssl: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    use_tls: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oauth_account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_security: Mapped[str | None] = mapped_column(String(16), nullable=True)
    smtp_security: Mapped[str | None] = mapped_column(String(16), nullable=True)
    connection_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    sync_cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_inbound_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    imap_uidvalidity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    imap_last_seen_uid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="NOT_CONFIGURED")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
