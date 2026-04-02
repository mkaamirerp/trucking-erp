"""IMAP adapter: incremental RFC822 fetch only (blocking I/O — run in executor)."""

from __future__ import annotations

from app.models.email_mailbox import TenantEmailMailbox
from app.services.email_ingestion_imap import imap_sync_incremental_sync

__all__ = ["imap_sync_incremental_sync", "fetch_incremental_rfc822_batch"]


def fetch_incremental_rfc822_batch(
    mailbox: TenantEmailMailbox,
    imap_password: str,
    *,
    max_messages: int = 100,
) -> tuple[list[tuple[int, bytes]], int, int]:
    """Thin wrapper named for adapter clarity; delegates to existing sync helper."""
    return imap_sync_incremental_sync(mailbox, imap_password, max_messages=max_messages)
