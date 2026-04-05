"""Schemas for tenant admin email mailbox config."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class GmailIngestionHealthOut(BaseModel):
    """Structured readiness for Gmail push → Pub/Sub → webhook → delta sync (tenant admin)."""

    oauth_connected: bool
    gmail_pubsub_topic_configured: bool
    history_cursor_present: bool
    watch_registered_and_valid: bool
    watch_expires_at: datetime | None = None
    last_webhook_at: datetime | None = None
    last_delta_sync_at: datetime | None = None
    automatic_ingestion_ready: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    proof_steps: list[str] = Field(default_factory=list)


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
    imap_security: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    reply_to: str | None = None
    smtp_security: str | None = None
    use_ssl: bool | None = None
    use_tls: bool | None = None

    oauth_provider: str | None = None
    oauth_account_email: str | None = None

    connection_status: str | None = None
    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_inbound_test_at: datetime | None = None
    last_outbound_test_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_inbound_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    imap_uidvalidity: int | None = None
    imap_last_seen_uid: int | None = None
    gmail_history_cursor_present: bool | None = None
    gmail_watch_active: bool | None = None
    gmail_watch_expires_at: datetime | None = None
    last_gmail_webhook_at: datetime | None = None
    # Gmail automatic ingestion (push → Pub/Sub → webhook); not implied by status=CONNECTED
    gmail_pubsub_topic_configured: bool | None = None
    gmail_automatic_ingestion_ready: bool | None = None
    gmail_automatic_ingestion_blockers: list[str] | None = None
    gmail_automatic_ingestion_warnings: list[str] | None = None

    ms_graph_subscription_id: str | None = None
    ms_graph_subscription_status: str | None = None
    ms_graph_subscription_expiration_at: datetime | None = None
    ms_graph_delta_cursor_present: bool | None = None
    ms_graph_last_notification_at: datetime | None = None
    ms_graph_last_delta_sync_at: datetime | None = None
    ms_graph_last_sync_status: str | None = None
    ms_graph_last_sync_error: str | None = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailConfigUpdate(BaseModel):
    """Update/create primary mailbox config. Secrets passed separately for security."""

    email_address: EmailStr
    display_name: str | None = None
    reply_to: str | None = Field(default=None, max_length=255)
    mailbox_type: str = Field(
        default="other",
        description="gmail, microsoft365 (OAuth), other (IMAP/SMTP manual)",
    )
    provider_name: str | None = None
    connection_mode: str = Field(default="manual", description="manual; oauth for Gmail / Microsoft 365 via Connect")
    inbound_enabled: bool = True
    outbound_enabled: bool = True
    is_primary: bool = True

    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = Field(default=None, description="Only sent when rotating; never returned")
    imap_security: str | None = Field(default=None, description="ssl | starttls | none")
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = Field(default=None, description="Only sent when rotating; never returned")
    smtp_security: str | None = Field(default=None, description="ssl | starttls | none")
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
    direction: str | None = None
    message: str | None = None
    last_tested_at: str | None = None
