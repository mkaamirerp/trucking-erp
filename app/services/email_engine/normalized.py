"""Provider-agnostic shapes handed to the shared ingestion engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedAttachment:
    """Attachment metadata (bytes fetched separately, e.g. Gmail API or future download worker)."""

    external_attachment_id: str
    filename: str | None
    mime_type: str | None
    size_bytes: int | None
    is_inline: bool
    provider_extra: dict[str, Any] | None = None


@dataclass
class NormalizedEmailMessage:
    """
    One inbound (or outbound) message after provider fetch + parse.
    All providers must populate this before calling the shared engine.
    """

    tenant_id: int
    mailbox_id: int | None
    provider: str
    external_message_id: str
    external_thread_id: str
    from_email: str | None
    to_json: list[dict[str, str]] | None
    cc_json: list[dict[str, str]] | None
    bcc_json: list[dict[str, str]] | None
    subject: str | None
    sent_at: datetime | None
    received_at: datetime | None
    snippet: str | None
    body_text: str | None
    body_html: str | None
    direction: str = "inbound"
    is_unread: bool = False
    attachments: list[NormalizedAttachment] = field(default_factory=list)


@dataclass
class NormalizedThreadRollup:
    """Denormalized thread fields; optional — engine can merge or recompute."""

    external_thread_id: str
    subject: str | None = None
    snippet: str | None = None
    participants_json: list[dict[str, str]] | None = None
    last_message_at: datetime | None = None
    message_count: int | None = None
    unread_count: int | None = None
