"""Gmail inbound ingestion: History API delta sync (no full inbox listing)."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.tenant_email_account import TenantEmailAccount
from app.services.email_intake_routing import apply_intake_routing_for_gmail_thread
from app.services.gmail_oauth import refresh_access_token
from app.utils.encryption import decrypt_secret

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


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


def _parse_date_header(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _headers_map(headers: list[dict[str, Any]] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        name = str(h.get("name") or "").strip().lower()
        if not name:
            continue
        out[name] = str(h.get("value") or "")
    return out


def _extract_text_plain(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    mime = (payload.get("mimeType") or "").lower()
    body = payload.get("body") or {}
    data = body.get("data")
    if mime == "text/plain" and isinstance(data, str) and data:
        try:
            padded = data + "=" * (-len(data) % 4)
            return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
        except Exception:
            return None
    for part in payload.get("parts") or []:
        extracted = _extract_text_plain(part)
        if extracted:
            return extracted
    return None


def _parse_address_list(raw: str | None) -> list[dict[str, str]]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    parsed: list[dict[str, str]] = []
    for p in parts:
        if "<" in p and ">" in p:
            name = p.split("<", 1)[0].strip().strip('"')
            email = p.split("<", 1)[1].split(">", 1)[0].strip()
            parsed.append({"name": name, "email": email})
        else:
            parsed.append({"email": p})
    return parsed


def _attachment_parts(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    out: list[dict[str, Any]] = []
    filename = str(payload.get("filename") or "").strip()
    body = payload.get("body") or {}
    attachment_id = str(body.get("attachmentId") or "").strip()
    if filename and attachment_id:
        headers = _headers_map(payload.get("headers"))
        disp = (headers.get("content-disposition") or "").lower()
        out.append(
            {
                "external_attachment_id": attachment_id,
                "filename": filename,
                "mime_type": payload.get("mimeType"),
                "size_bytes": body.get("size"),
                "is_inline": "inline" in disp and "attachment" not in disp,
            }
        )
    for part in payload.get("parts") or []:
        out.extend(_attachment_parts(part))
    return out


def _participant_emails(
    from_email: str | None,
    to_json: list[dict[str, str]] | None,
    cc_json: list[dict[str, str]] | None,
    bcc_json: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []

    def _push(email: str | None) -> None:
        if not email:
            return
        e = email.strip().lower()
        if not e or e in seen:
            return
        seen.add(e)
        out.append({"email": e})

    _push(from_email)
    for group in (to_json or [], cc_json or [], bcc_json or []):
        for addr in group:
            _push(addr.get("email"))
    return out


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
    """Fetch Gmail thread (format=full) and upsert thread, messages, attachments. Returns counts (msgs, atts, 1 thread)."""
    td = await _gmail_get_json(access_token, f"/threads/{quote(ext_thread_id, safe='')}", params={"format": "full"})
    snippet = td.get("snippet")
    existing_thread = await tenant_db.scalar(
        select(EmailThread).where(
            EmailThread.tenant_id == tenant_id,
            EmailThread.provider == "gmail",
            EmailThread.external_thread_id == ext_thread_id,
        )
    )
    if not existing_thread:
        existing_thread = EmailThread(
            tenant_id=tenant_id,
            provider="gmail",
            external_thread_id=ext_thread_id,
            status="active",
        )
        tenant_db.add(existing_thread)
        await tenant_db.flush()

    msgs = td.get("messages") or []
    last_message_at: datetime | None = None
    unread_count = 0
    subject: str | None = None
    participants: list[dict[str, str]] = []

    messages_touched = 0
    attachments_touched = 0

    for gm in msgs:
        ext_msg_id = str(gm.get("id") or "").strip()
        if not ext_msg_id:
            continue
        payload = gm.get("payload") or {}
        hdr = _headers_map(payload.get("headers"))
        from_email = hdr.get("from")
        to_json = _parse_address_list(hdr.get("to"))
        cc_json = _parse_address_list(hdr.get("cc"))
        bcc_json = _parse_address_list(hdr.get("bcc"))
        msg_subject = hdr.get("subject")
        sent_at = _parse_date_header(hdr.get("date"))
        internal_ms = gm.get("internalDate")
        received_at = None
        if internal_ms is not None:
            try:
                received_at = datetime.fromtimestamp(int(internal_ms) / 1000.0, tz=timezone.utc)
            except Exception:
                received_at = None
        msg_dt = received_at or sent_at
        if msg_dt and (last_message_at is None or msg_dt > last_message_at):
            last_message_at = msg_dt
        if "UNREAD" in (gm.get("labelIds") or []):
            unread_count += 1
        if not subject and msg_subject:
            subject = msg_subject
        participants = _participant_emails(from_email, to_json, cc_json, bcc_json) or participants
        body_text = _extract_text_plain(payload)
        att_parts = _attachment_parts(payload)
        has_attachments = bool(att_parts)

        existing_msg = await tenant_db.scalar(
            select(EmailMessage).where(
                EmailMessage.tenant_id == tenant_id,
                EmailMessage.provider == "gmail",
                EmailMessage.external_message_id == ext_msg_id,
            )
        )
        if existing_msg:
            existing_msg.thread_id = existing_thread.id
            existing_msg.external_thread_id = ext_thread_id
            existing_msg.direction = existing_msg.direction or "inbound"
            existing_msg.from_email = from_email
            existing_msg.to_json = to_json
            existing_msg.cc_json = cc_json
            existing_msg.bcc_json = bcc_json
            existing_msg.subject = msg_subject
            existing_msg.sent_at = sent_at
            existing_msg.received_at = received_at
            existing_msg.snippet = gm.get("snippet")
            existing_msg.body_text = body_text
            existing_msg.has_attachments = has_attachments
            existing_msg.updated_at = datetime.now(timezone.utc)
        else:
            tenant_db.add(
                EmailMessage(
                    tenant_id=tenant_id,
                    thread_id=existing_thread.id,
                    provider="gmail",
                    external_message_id=ext_msg_id,
                    external_thread_id=ext_thread_id,
                    direction="inbound",
                    from_email=from_email,
                    to_json=to_json,
                    cc_json=cc_json,
                    bcc_json=bcc_json,
                    subject=msg_subject,
                    sent_at=sent_at,
                    received_at=received_at,
                    snippet=gm.get("snippet"),
                    body_text=body_text,
                    has_attachments=has_attachments,
                )
            )
            await tenant_db.flush()
            existing_msg = await tenant_db.scalar(
                select(EmailMessage).where(
                    EmailMessage.tenant_id == tenant_id,
                    EmailMessage.provider == "gmail",
                    EmailMessage.external_message_id == ext_msg_id,
                )
            )
        messages_touched += 1

        for ap in att_parts:
            if not existing_msg:
                continue
            existing_attachment = await tenant_db.scalar(
                select(EmailMessageAttachment).where(
                    EmailMessageAttachment.tenant_id == tenant_id,
                    EmailMessageAttachment.provider == "gmail",
                    EmailMessageAttachment.message_id == existing_msg.id,
                    EmailMessageAttachment.external_attachment_id == ap["external_attachment_id"],
                )
            )
            if existing_attachment:
                existing_attachment.filename = ap.get("filename")
                existing_attachment.mime_type = ap.get("mime_type")
                existing_attachment.size_bytes = ap.get("size_bytes")
                existing_attachment.is_inline = bool(ap.get("is_inline"))
                existing_attachment.updated_at = datetime.now(timezone.utc)
            else:
                tenant_db.add(
                    EmailMessageAttachment(
                        tenant_id=tenant_id,
                        message_id=existing_msg.id,
                        provider="gmail",
                        external_attachment_id=ap["external_attachment_id"],
                        filename=ap.get("filename"),
                        mime_type=ap.get("mime_type"),
                        size_bytes=ap.get("size_bytes"),
                        is_inline=bool(ap.get("is_inline")),
                        download_status="metadata_only",
                    )
                )
            attachments_touched += 1

    existing_thread.subject = subject
    existing_thread.participants_json = participants
    existing_thread.snippet = snippet
    existing_thread.last_message_at = last_message_at
    existing_thread.message_count = len(msgs)
    existing_thread.unread_count = unread_count
    existing_thread.updated_at = datetime.now(timezone.utc)
    try:
        await apply_intake_routing_for_gmail_thread(tenant_db, tenant_id, existing_thread.id, access_token)
    except Exception as exc:
        logger.warning("email intake routing skipped: %s", exc)

    return messages_touched, attachments_touched, 1


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
