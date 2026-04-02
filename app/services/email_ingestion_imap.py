"""
Incremental IMAP ingestion for mailbox_type=other (non-Gmail / non-Microsoft).
Uses UIDVALIDITY + last seen UID; idempotent upserts on Message-ID / UID composite.
"""

from __future__ import annotations

import asyncio
import imaplib
import json
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_mailbox import TenantEmailMailbox
from app.models.platform_integration import TenantIntegrationSecret
from app.services.email_engine.email_ingestion_engine import IngestionContext, ingest_normalized_thread
from app.services.email_engine.message_normalizer import rfc822_bytes_to_normalized
from app.utils.encryption import decrypt_secret

logger = logging.getLogger(__name__)

EMAIL_PROVIDER_OTHER = "other"


def _imap_security_mode(mailbox: TenantEmailMailbox) -> str:
    sec = (mailbox.imap_security or "").strip().lower()
    if sec in ("ssl", "starttls", "none"):
        return sec
    if mailbox.use_ssl:
        return "ssl"
    return "starttls"


def _smtp_security_mode(mailbox: TenantEmailMailbox) -> str:
    sec = (mailbox.smtp_security or "").strip().lower()
    if sec in ("ssl", "starttls", "none"):
        return sec
    port = mailbox.smtp_port or 587
    if port == 465:
        return "ssl"
    return "starttls"


def load_mailbox_secret_json(secret_row: TenantIntegrationSecret | None) -> dict[str, Any]:
    if not secret_row:
        return {}
    try:
        dec = decrypt_secret(secret_row.encrypted_payload)
        return json.loads(dec.decode("utf-8"))
    except Exception:
        return {}


def imap_test_connection_sync(
    mailbox: TenantEmailMailbox,
    imap_password: str | None,
) -> None:
    """Raises on failure."""
    host = mailbox.imap_host
    user = mailbox.imap_username
    port = int(mailbox.imap_port or 993)
    mode = _imap_security_mode(mailbox)
    if not host or not user or not imap_password:
        raise ValueError("IMAP host, username, and password required")

    if mode == "ssl":
        ctx = ssl.create_default_context()
        conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    else:
        conn = imaplib.IMAP4(host, port)
        if mode == "starttls":
            conn.starttls(ssl.create_default_context())
    try:
        conn.login(user, imap_password)
        conn.select("INBOX", readonly=True)
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def smtp_test_connection_sync(
    mailbox: TenantEmailMailbox,
    smtp_password: str | None,
) -> None:
    host = mailbox.smtp_host
    user = mailbox.smtp_username
    port = int(mailbox.smtp_port or 587)
    mode = _smtp_security_mode(mailbox)
    if not host or not user or not smtp_password:
        raise ValueError("SMTP host, username, and password required")

    if mode == "ssl":
        server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(host, port)
        try:
            server.ehlo()
            if mode == "starttls":
                server.starttls(context=ssl.create_default_context())
            server.ehlo()
        except Exception:
            server.quit()
            raise
    try:
        server.login(user, smtp_password)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _parse_uidvalidity(select_response: bytes) -> int | None:
    if not select_response:
        return None
    text = select_response.decode("utf-8", errors="replace")
    m = re.search(r"UIDVALIDITY\s+(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def imap_sync_incremental_sync(
    mailbox: TenantEmailMailbox,
    imap_password: str,
    *,
    max_messages: int = 100,
) -> tuple[list[tuple[int, bytes]], int, int]:
    """
    Returns (list of (uid, rfc822_bytes), uidvalidity, new_max_uid).
    Only UIDs greater than last_seen_uid (or capped first-harvest) are fetched.
    Does not mutate ORM objects (thread-safe for executor).
    """
    host = mailbox.imap_host
    user = mailbox.imap_username
    port = int(mailbox.imap_port or 993)
    mode = _imap_security_mode(mailbox)
    if not host or not user or not imap_password:
        raise ValueError("IMAP host, username, and password required")

    if mode == "ssl":
        conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())
    else:
        conn = imaplib.IMAP4(host, port)
        if mode == "starttls":
            conn.starttls(ssl.create_default_context())
    results: list[tuple[int, bytes]] = []
    uidvalidity: int = 0
    stored_v = mailbox.imap_uidvalidity
    last_seen = mailbox.imap_last_seen_uid
    new_max_uid = int(last_seen or 0)

    try:
        conn.login(user, imap_password)
        typ, data = conn.select("INBOX", readonly=True)
        if typ != "OK" or not data or not data[0]:
            raise RuntimeError("IMAP SELECT INBOX failed")
        uidvalidity = _parse_uidvalidity(data[0] or b"") or 0

        if stored_v is not None and uidvalidity and int(stored_v) != uidvalidity:
            last_seen = None

        last = last_seen
        if last is None or int(last) == 0:
            typ, data = conn.uid("SEARCH", None, "ALL")
            if typ != "OK" or not data or not data[0]:
                uids = []
            else:
                uids = [int(x) for x in data[0].split() if x.isdigit()]
            uids.sort()
            uids = uids[-max_messages:] if len(uids) > max_messages else uids
        else:
            typ, data = conn.uid("SEARCH", None, f"(UID {int(last) + 1}:*)")
            if typ != "OK" or not data or not data[0]:
                uids = []
            else:
                uids = [int(x) for x in data[0].split() if x.isdigit()]

        for uid in uids:
            typ, msg_data = conn.uid("FETCH", str(uid), "(RFC822)")
            if typ != "OK" or not msg_data:
                continue
            raw: bytes | None = None
            for item in msg_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw = item[1]
                    break
            if raw:
                results.append((uid, raw))
                new_max_uid = max(new_max_uid, uid)
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    if not uidvalidity and mailbox.imap_uidvalidity:
        uidvalidity = int(mailbox.imap_uidvalidity)
    return results, uidvalidity, new_max_uid


@dataclass
class ImapSyncResult:
    tenant_id: int
    provider: str
    threads_upserted: int
    messages_upserted: int
    attachments_upserted: int
    uids_fetched: int


async def sync_other_imap_inbox_for_tenant(
    tenant_db: AsyncSession,
    platform_db: AsyncSession,
    tenant_id: int,
    *,
    max_messages: int = 100,
) -> ImapSyncResult:
    """
    Scheduled/operator entrypoint: fetch new IMAP messages since last UID state, persist, intake=routing review-only.
    """
    mailbox = await tenant_db.scalar(
        select(TenantEmailMailbox)
        .where(
            TenantEmailMailbox.tenant_id == tenant_id,
            TenantEmailMailbox.is_primary == True,
        )
        .limit(1)
    )
    if not mailbox:
        raise ValueError("No primary mailbox")
    mtype = (mailbox.mailbox_type or "").strip().lower()
    if mtype != EMAIL_PROVIDER_OTHER:
        raise ValueError("Primary mailbox is not other/IMAP manual provider")
    if not mailbox.credential_ref:
        raise ValueError("Mailbox has no credentials")
    secret = await platform_db.scalar(
        select(TenantIntegrationSecret).where(
            TenantIntegrationSecret.tenant_id == tenant_id,
            TenantIntegrationSecret.credential_ref == mailbox.credential_ref,
        )
    )
    data = load_mailbox_secret_json(secret)
    imap_pw = data.get("imap_password")
    if not imap_pw:
        raise ValueError("IMAP password not stored")

    loop = asyncio.get_event_loop()

    def _run_sync():
        return imap_sync_incremental_sync(mailbox, imap_pw, max_messages=max_messages)

    try:
        fetched, uidval, new_max = await loop.run_in_executor(None, _run_sync)
    except Exception as exc:
        now = datetime.now(timezone.utc)
        mailbox.last_sync_at = now
        mailbox.last_sync_status = "error"
        mailbox.last_sync_error = (str(exc) or "imap_sync_failed")[:2000]
        mailbox.updated_at = now
        await tenant_db.commit()
        raise

    threads_touched: set[str] = set()
    msg_count = 0
    att_count = 0
    ctx = IngestionContext(tenant_id=tenant_id, provider=EMAIL_PROVIDER_OTHER, gmail_access_token=None)

    for uid, raw in fetched:
        rollup, norm = rfc822_bytes_to_normalized(
            tenant_id, int(mailbox.id), EMAIL_PROVIDER_OTHER, uid, int(uidval or 0), raw
        )
        _thread_row, d_m, d_a = await ingest_normalized_thread(tenant_db, ctx, rollup, [norm])
        threads_touched.add(rollup.external_thread_id)
        msg_count += d_m
        att_count += d_a

    now = datetime.now(timezone.utc)
    mailbox.imap_uidvalidity = uidval or mailbox.imap_uidvalidity
    if new_max > 0:
        mailbox.imap_last_seen_uid = new_max
    mailbox.last_sync_at = now
    mailbox.last_sync_status = "ok" if fetched else "ok"
    mailbox.last_sync_error = None
    mailbox.last_error_message = None
    mailbox.connection_status = "CONNECTED"
    mailbox.updated_at = now

    await tenant_db.commit()

    return ImapSyncResult(
        tenant_id=tenant_id,
        provider=EMAIL_PROVIDER_OTHER,
        threads_upserted=len(threads_touched),
        messages_upserted=msg_count,
        attachments_upserted=att_count,
        uids_fetched=len(fetched),
    )


async def schedule_other_imap_sync_placeholder(tenant_id: int) -> None:
    """Hook for future cron / worker: call sync_other_imap_inbox_for_tenant with platform + tenant sessions."""
    _ = tenant_id
    logger.debug("schedule_other_imap_sync_placeholder: implement worker dispatch")
