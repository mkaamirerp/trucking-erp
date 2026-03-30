"""Schemas for tenant admin email mailbox config."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class EmailConfigOut(BaseModel):
    """Response shape for primary mailbox config. Never includes secrets."""

    id: int
    tenant_id: int
    email_address: str
    display_name: str | None = None
    mailbox_type: str
    provider_name: str | None = None
    connection_mode: str
    is_primary: bool
    is_active: bool
    inbound_enabled: bool
    outbound_enabled: bool
    status: str

    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    use_ssl: bool | None = None
    use_tls: bool | None = None

    oauth_provider: str | None = None
    oauth_account_email: str | None = None

    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    # Gmail OAuth (tenant_email_accounts): last successful History/delta ingestion run; None for manual IMAP rows.
    last_inbound_sync_at: datetime | None = None
    # Gmail operator diagnostics (null / false when mailbox is manual IMAP row).
    gmail_history_cursor_present: bool | None = None
    gmail_watch_active: bool | None = None
    gmail_watch_expires_at: datetime | None = None
    last_gmail_webhook_at: datetime | None = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailConfigUpdate(BaseModel):
    """Update/create primary mailbox config. Secrets passed separately for security."""

    email_address: EmailStr
    display_name: str | None = None
    mailbox_type: str = Field(default="imap", description="gmail, microsoft, imap")
    provider_name: str | None = None
    connection_mode: str = Field(default="manual", description="manual only; oauth not yet implemented")
    inbound_enabled: bool = True
    outbound_enabled: bool = True

    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = Field(default=None, description="Only sent when updating; never returned")
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = Field(default=None, description="Only sent when updating; never returned")
    use_ssl: bool | None = None
    use_tls: bool | None = None

    oauth_provider: str | None = None
    oauth_account_email: str | None = None
    oauth_access_token: str | None = Field(default=None, description="Not yet implemented")
    oauth_refresh_token: str | None = Field(default=None, description="Not yet implemented")


class EmailConfigTestOut(BaseModel):
    """Result of connection test."""

    ok: bool
    status: str
    message: str | None = None
    last_tested_at: str | None = None
