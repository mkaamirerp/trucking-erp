"""Gmail inbound ingestion: History API delta sync. Fetch + normalize here; persistence/routing in email_engine."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_email_account import TenantEmailAccount
from app.services.email_engine.email_ingestion_engine import IngestionContext, ingest_normalized_thread
from app.services.email_engine.message_normalizer import gmail_full_thread_to_normalized
from app.services.email_engine.message_normalizer import (
    attachment_parts_from_gmail_payload as _attachment_parts,
)
from app.services.email_engine.message_normalizer import (
    extract_text_plain_from_gmail_payload as _extract_text_plain,
)
from app.services.email_engine.message_normalizer import headers_map as _headers_map
from app.services.email_engine.message_normalizer import parse_address_list as _parse_address_list
from app.services.email_engine.message_normalizer import parse_date_header as _parse_date_header
from app.services.email_engine.message_normalizer import participant_emails as _participant_emails
from app.services.gmail_oauth import refresh_access_token
from app.utils.encryption import decrypt_secret

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Re-export normalizer helpers for legacy imports (e.g. IMAP path — prefer email_engine.message_normalizer).
__all__ = [
    "GmailSyncResult",
    "GMAIL_API_BASE",
    "bootstrap_gmail_history_cursor",
    "sync_gmail_delta_for_tenant",
    "sync_gmail_inbox_for_tenant",
    "decode_pubsub_gmail_notification",
    "_gmail_http_get",
    "_gmail_get_json",
]


@dataclass
class GmailSyncResult:
    tenant_id: int
    provider: str
    threads_upserted: int
    messages_upserted: int
    attachments_upserted: int
    threads_scanned: int
    history_pages: int = 0
    history_cursor_advanced: bool = False


async def _gmail_http_get(access_token: str, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await client.get(
            f"{GMAIL_API_BASE}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {access_token}"},
        )


async def _gmail_get_json(access_token: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = await _gmail_http_get(access_token, path, params=params)
    resp.raise_for_status()
    return resp.json()


async def bootstrap_gmail_history_cursor(tenant_db: AsyncSession, tenant_id: int) -> str | None:
    """
    Set gmail_history_id from users.profile when missing (no messages pulled — baseline for future deltas).
    Returns new history id or None if skipped/failed.
    """
    acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if not acc:
        return None
    if acc.gmail_history_id:
        return str(acc.gmail_history_id)

    refresh_token = decrypt_secret(acc.refresh_token_encrypted).decode("utf-8")
    tok = await refresh_access_token(refresh_token)
    access_token = tok.get("access_token")
    if not access_token:
        return None
    profile = await _gmail_get_json(access_token, "/profile")
    hid = str(profile.get("historyId") or "").strip()
    if not hid:
        return None
    acc.gmail_history_id = hid
    acc.last_error = None
    acc.updated_at = datetime.now(timezone.utc)
    await tenant_db.flush()
    return hid


async def _upsert_full_thread_from_gmail(
    tenant_db: AsyncSession,
    tenant_id: int,
    access_token: str,
    ext_thread_id: str,
) -> tuple[int, int, int]:
    """Fetch Gmail thread (format=full), normalize, run shared ingestion engine."""
    from app.services.email_providers.gmail_adapter import fetch_thread_full

    td = await fetch_thread_full(access_token, ext_thread_id)
    rollup, messages = gmail_full_thread_to_normalized(tenant_id, None, "gmail", td)
    ctx = IngestionContext(tenant_id=tenant_id, provider="gmail", gmail_access_token=access_token)
    _thread_row, m, a = await ingest_normalized_thread(tenant_db, ctx, rollup, messages)
    return m, a, 1


async def sync_gmail_delta_for_tenant(tenant_db: AsyncSession, tenant_id: int) -> GmailSyncResult:
    """
    Apply Gmail History API deltas since stored gmail_history_id. Idempotent upserts.
    Advances cursor to current profile historyId after successful page drain.
    """
    acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if not acc:
        raise ValueError("No connected Gmail account for tenant")

    refresh_token = decrypt_secret(acc.refresh_token_encrypted).decode("utf-8")
    tok = await refresh_access_token(refresh_token)
    access_token = tok.get("access_token")
    if not access_token:
        raise ValueError("Failed to refresh Gmail access token")

    profile = await _gmail_get_json(access_token, "/profile")
    current_hid = str(profile.get("historyId") or "").strip()
    if not current_hid:
        raise ValueError("Gmail profile missing historyId")

    if not acc.gmail_history_id:
        acc.gmail_history_id = current_hid
        acc.last_sync_at = datetime.now(timezone.utc)
        acc.last_error = None
        acc.updated_at = datetime.now(timezone.utc)
        await tenant_db.commit()
        return GmailSyncResult(
            tenant_id=tenant_id,
            provider="gmail",
            threads_upserted=0,
            messages_upserted=0,
            attachments_upserted=0,
            threads_scanned=0,
            history_pages=0,
            history_cursor_advanced=True,
        )

    thread_ids: set[str] = set()
    pages = 0
    start_id = str(acc.gmail_history_id)
    page_token: str | None = None
    latest_list_hid: str | None = None

    while True:
        params: dict[str, Any] = {
            "startHistoryId": start_id,
            "historyTypes": "messageAdded",
        }
        if page_token:
            params["pageToken"] = page_token
        resp = await _gmail_http_get(access_token, "/history", params=params)
        if resp.status_code == 404:
            acc.gmail_history_id = current_hid
            acc.last_error = "history_cursor_reset_stale_start_history_id"
            acc.last_sync_at = datetime.now(timezone.utc)
            acc.updated_at = datetime.now(timezone.utc)
            await tenant_db.commit()
            return GmailSyncResult(
                tenant_id=tenant_id,
                provider="gmail",
                threads_upserted=0,
                messages_upserted=0,
                attachments_upserted=0,
                threads_scanned=0,
                history_pages=pages,
                history_cursor_advanced=True,
            )
        resp.raise_for_status()
        page = resp.json()
        pages += 1
        top_hid = str(page.get("historyId") or "").strip()
        if top_hid:
            latest_list_hid = top_hid
        for h in page.get("history") or []:
            for ma in h.get("messagesAdded") or []:
                msg = (ma.get("message") or {}) if isinstance(ma, dict) else {}
                tid = str(msg.get("threadId") or "").strip()
                if tid:
                    thread_ids.add(tid)
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    threads_upserted = 0
    messages_upserted = 0
    attachments_upserted = 0
    for tid in sorted(thread_ids):
        m, a, _ = await _upsert_full_thread_from_gmail(tenant_db, tenant_id, access_token, tid)
        messages_upserted += m
        attachments_upserted += a
        threads_upserted += 1

    new_cursor = latest_list_hid or current_hid
    if new_cursor:
        acc.gmail_history_id = new_cursor
    acc.last_sync_at = datetime.now(timezone.utc)
    acc.last_error = None
    acc.updated_at = datetime.now(timezone.utc)
    await tenant_db.commit()

    return GmailSyncResult(
        tenant_id=tenant_id,
        provider="gmail",
        threads_upserted=threads_upserted,
        messages_upserted=messages_upserted,
        attachments_upserted=attachments_upserted,
        threads_scanned=len(thread_ids),
        history_pages=pages,
        history_cursor_advanced=bool(new_cursor),
    )


async def sync_gmail_inbox_for_tenant(
    tenant_db: AsyncSession,
    tenant_id: int,
    *,
    max_threads: int = 30,
) -> GmailSyncResult:
    """
    On-demand sync: History API delta only. `max_threads` is ignored (kept for API compatibility).
    """
    _ = max_threads
    return await sync_gmail_delta_for_tenant(tenant_db, tenant_id)


def decode_pubsub_gmail_notification(body: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Parse Cloud Pub/Sub push envelope body. Returns (email_address, history_id_str) from Gmail notification.
    """
    msg = body.get("message")
    if not isinstance(msg, dict):
        return None, None
    raw = msg.get("data")
    if not isinstance(raw, str) or not raw:
        return None, None
    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        inner = json.loads(decoded)
    except Exception:
        return None, None
    if not isinstance(inner, dict):
        return None, None
    email = str(inner.get("emailAddress") or inner.get("email_address") or "").strip() or None
    hid = inner.get("historyId")
    hid_str = str(hid).strip() if hid is not None else None
    return email, hid_str
