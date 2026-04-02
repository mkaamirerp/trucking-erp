"""Platform DB: map Gmail mailbox address → tenant_id for server-to-server ingestion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import PlatformGmailMailboxIndex

logger = logging.getLogger(__name__)


def normalize_gmail_address(email: str | None) -> str | None:
    if not email:
        return None
    e = email.strip().lower()
    return e or None


async def upsert_gmail_mailbox_tenant_mapping(
    platform_db: AsyncSession, *, tenant_id: int, gmail_address: str | None
) -> None:
    norm = normalize_gmail_address(gmail_address)
    if not norm:
        return
    row = await platform_db.scalar(
        select(PlatformGmailMailboxIndex).where(PlatformGmailMailboxIndex.gmail_address_norm == norm).limit(1)
    )
    now = datetime.now(timezone.utc)
    if row:
        if int(row.tenant_id) != int(tenant_id):
            logger.error(
                "gmail_mailbox_index conflict: %s already mapped to tenant_id=%s (refusing remap to %s)",
                norm[:3] + "***",
                row.tenant_id,
                tenant_id,
            )
            return
        row.updated_at = now
        return
    platform_db.add(
        PlatformGmailMailboxIndex(
            tenant_id=int(tenant_id),
            gmail_address_norm=norm,
            created_at=now,
            updated_at=now,
        )
    )


async def delete_gmail_mailbox_mappings_for_tenant(platform_db: AsyncSession, *, tenant_id: int) -> None:
    await platform_db.execute(
        delete(PlatformGmailMailboxIndex).where(PlatformGmailMailboxIndex.tenant_id == int(tenant_id))
    )


async def resolve_tenant_id_for_gmail_address(
    platform_db: AsyncSession, gmail_address: str | None
) -> int | None:
    norm = normalize_gmail_address(gmail_address)
    if not norm:
        return None
    row = await platform_db.scalar(
        select(PlatformGmailMailboxIndex).where(PlatformGmailMailboxIndex.gmail_address_norm == norm).limit(1)
    )
    return int(row.tenant_id) if row else None
