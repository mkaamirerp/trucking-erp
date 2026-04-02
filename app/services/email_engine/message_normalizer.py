"""Parse provider-specific payloads into Normalized* structures (no DB, no routing)."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Any

from app.services.email_engine.normalized import NormalizedAttachment, NormalizedEmailMessage, NormalizedThreadRollup

_MESSAGE_ID_RE = re.compile(r"<([^>]+)>")


def parse_date_header(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def headers_map(headers: list[dict[str, Any]] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        name = str(h.get("name") or "").strip().lower()
        if not name:
            continue
        out[name] = str(h.get("value") or "")
    return out


def extract_text_plain_from_gmail_payload(payload: dict[str, Any] | None) -> str | None:
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
        extracted = extract_text_plain_from_gmail_payload(part)
        if extracted:
            return extracted
    return None


def parse_address_list(raw: str | None) -> list[dict[str, str]]:
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


def attachment_parts_from_gmail_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    out: list[dict[str, Any]] = []
    filename = str(payload.get("filename") or "").strip()
    body = payload.get("body") or {}
    attachment_id = str(body.get("attachmentId") or "").strip()
    if filename and attachment_id:
        hdrs = headers_map(payload.get("headers"))
        disp = (hdrs.get("content-disposition") or "").lower()
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
        out.extend(attachment_parts_from_gmail_payload(part))
    return out


def participant_emails(
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


def _norm_msg_id(raw: str | None) -> str | None:
    if not raw:
        return None
    m = _MESSAGE_ID_RE.search(raw)
    if m:
        return m.group(1).strip()
    s = raw.strip().strip("<>").strip()
    return s or None


def thread_external_id_from_rfc822(msg: Message) -> str:
    refs = msg.get("References")
    if refs:
        parts = _MESSAGE_ID_RE.findall(refs)
        if parts:
            return parts[0].strip()
    irt = msg.get("In-Reply-To")
    mid_irt = _norm_msg_id(irt)
    if mid_irt:
        return mid_irt
    mid = _norm_msg_id(msg.get("Message-ID"))
    if mid:
        return mid
    return "orphan-no-message-id"


def external_message_id_from_parts(uid: int, uidvalidity: int, msg: Message) -> str:
    mid = _norm_msg_id(msg.get("Message-ID"))
    if mid:
        return mid
    return f"{uidvalidity}:{uid}"


def text_body_from_rfc822(msg: Message) -> str | None:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not part.get_content_disposition():
                try:
                    return part.get_content()
                except Exception:
                    continue
        return None
    if msg.get_content_type() == "text/plain":
        try:
            return msg.get_content()
        except Exception:
            return None
    return None


def html_body_from_rfc822(msg: Message) -> str | None:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html" and not part.get_content_disposition():
                try:
                    return part.get_content()
                except Exception:
                    continue
        return None
    if msg.get_content_type() == "text/html":
        try:
            return msg.get_content()
        except Exception:
            return None
    return None


def attachments_meta_from_rfc822(msg: Message) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    idx = 0
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disp = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if disp == "attachment" or (filename and filename.strip()):
            idx += 1
            ext_id = f"part-{idx}"
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0
            inline = disp == "inline"
            out.append(
                {
                    "external_attachment_id": ext_id,
                    "filename": filename or "unnamed",
                    "mime_type": ctype,
                    "size_bytes": size,
                    "is_inline": inline,
                }
            )
    return out


def gmail_full_thread_to_normalized(
    tenant_id: int,
    mailbox_id: int | None,
    provider: str,
    td: dict[str, Any],
) -> tuple[NormalizedThreadRollup, list[NormalizedEmailMessage]]:
    """Convert Gmail `users.threads.get` JSON (format=full) into normalized shapes."""
    ext_thread_id = str(td.get("id") or "").strip()
    if not ext_thread_id:
        raise ValueError("Gmail thread payload missing id")

    snippet = td.get("snippet")
    msgs = td.get("messages") or []
    last_message_at: datetime | None = None
    unread_count = 0
    subject: str | None = None
    participants: list[dict[str, str]] = []
    normalized_messages: list[NormalizedEmailMessage] = []

    for gm in msgs:
        ext_msg_id = str(gm.get("id") or "").strip()
        if not ext_msg_id:
            continue
        payload = gm.get("payload") or {}
        hdr = headers_map(payload.get("headers"))
        from_email = hdr.get("from")
        to_json = parse_address_list(hdr.get("to"))
        cc_json = parse_address_list(hdr.get("cc"))
        bcc_json = parse_address_list(hdr.get("bcc"))
        msg_subject = hdr.get("subject")
        sent_at = parse_date_header(hdr.get("date"))
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
        is_unread = "UNREAD" in (gm.get("labelIds") or [])
        if is_unread:
            unread_count += 1
        if not subject and msg_subject:
            subject = msg_subject
        participants = participant_emails(from_email, to_json, cc_json, bcc_json) or participants
        body_text = extract_text_plain_from_gmail_payload(payload)
        att_raw = attachment_parts_from_gmail_payload(payload)
        attachments = [
            NormalizedAttachment(
                external_attachment_id=str(ap["external_attachment_id"]),
                filename=ap.get("filename"),
                mime_type=ap.get("mime_type"),
                size_bytes=int(ap["size_bytes"]) if ap.get("size_bytes") is not None else None,
                is_inline=bool(ap.get("is_inline")),
                provider_extra=None,
            )
            for ap in att_raw
        ]
        normalized_messages.append(
            NormalizedEmailMessage(
                tenant_id=tenant_id,
                mailbox_id=mailbox_id,
                provider=provider,
                external_message_id=ext_msg_id,
                external_thread_id=ext_thread_id,
                from_email=from_email,
                to_json=to_json,
                cc_json=cc_json,
                bcc_json=bcc_json,
                subject=msg_subject,
                sent_at=sent_at,
                received_at=received_at,
                snippet=gm.get("snippet"),
                body_text=body_text,
                body_html=None,
                direction="inbound",
                is_unread=is_unread,
                attachments=attachments,
            )
        )

    rollup = NormalizedThreadRollup(
        external_thread_id=ext_thread_id,
        subject=subject,
        snippet=snippet,
        participants_json=participants,
        last_message_at=last_message_at,
        message_count=len(msgs),
        unread_count=unread_count,
    )
    return rollup, normalized_messages


def rfc822_bytes_to_normalized(
    tenant_id: int,
    mailbox_id: int | None,
    provider: str,
    uid: int,
    uidvalidity: int,
    raw: bytes,
) -> tuple[NormalizedThreadRollup, NormalizedEmailMessage]:
    parser = BytesParser(policy=policy.default)
    msg = parser.parsebytes(raw)
    ext_thread = thread_external_id_from_rfc822(msg)
    ext_mid = external_message_id_from_parts(uid, uidvalidity, msg)
    from_hdr = msg.get("From")
    to_hdr = msg.get("To")
    cc_hdr = msg.get("Cc")
    subj = msg.get("Subject")
    sent_at = parse_date_header(msg.get("Date"))
    received_at = sent_at or datetime.now(timezone.utc)
    body_text = text_body_from_rfc822(msg)
    body_html = html_body_from_rfc822(msg)
    snippet = (body_text or subj or "")[:500]
    to_json = parse_address_list(to_hdr)
    cc_json = parse_address_list(cc_hdr)
    participants = participant_emails(from_hdr, to_json, cc_json, None)
    atts_raw = attachments_meta_from_rfc822(msg)
    attachments = [
        NormalizedAttachment(
            external_attachment_id=str(ap["external_attachment_id"]),
            filename=ap.get("filename"),
            mime_type=ap.get("mime_type"),
            size_bytes=ap.get("size_bytes"),
            is_inline=bool(ap.get("is_inline")),
            provider_extra=None,
        )
        for ap in atts_raw
    ]
    norm = NormalizedEmailMessage(
        tenant_id=tenant_id,
        mailbox_id=mailbox_id,
        provider=provider,
        external_message_id=ext_mid,
        external_thread_id=ext_thread,
        from_email=from_hdr,
        to_json=to_json,
        cc_json=cc_json,
        bcc_json=None,
        subject=subj,
        sent_at=sent_at,
        received_at=received_at,
        snippet=snippet,
        body_text=body_text,
        body_html=body_html,
        direction="inbound",
        is_unread=False,
        attachments=attachments,
    )
    rollup = NormalizedThreadRollup(
        external_thread_id=ext_thread,
        subject=subj,
        snippet=snippet,
        participants_json=participants,
        last_message_at=received_at,
        message_count=None,
        unread_count=None,
    )
    return rollup, norm


def _graph_single_address(obj: dict[str, Any] | None) -> str | None:
    if not obj:
        return None
    ea = obj.get("emailAddress")
    if isinstance(ea, dict):
        return (ea.get("address") or "").strip() or None
    return None


def _graph_recipient_list_graph(recips: list[Any] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in recips or []:
        if not isinstance(r, dict):
            continue
        ea = r.get("emailAddress") or {}
        addr = str(ea.get("address") or "").strip()
        name = str(ea.get("name") or "").strip()
        if addr:
            out.append({"name": name, "email": addr})
    return out


def parse_graph_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        s = raw.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def graph_api_message_to_normalized(
    tenant_id: int,
    mailbox_id: int | None,
    provider: str,
    msg: dict[str, Any],
    *,
    attachments: list[dict[str, Any]] | None = None,
) -> tuple[NormalizedThreadRollup, NormalizedEmailMessage]:
    """Map Microsoft Graph message JSON (+ optional pre-fetched attachment metadata) to normalized shapes."""
    ext_mid = str(msg.get("id") or "").strip()
    if not ext_mid:
        raise ValueError("Graph message missing id")
    ext_thread = str(msg.get("conversationId") or ext_mid).strip()
    subj = msg.get("subject")
    body = msg.get("body") or {}
    ctype = (body.get("contentType") or "text").lower()
    content = body.get("content") or ""
    body_text = content if ctype == "text" else None
    body_html = content if ctype == "html" else None
    snippet = (msg.get("bodyPreview") or "")[:500] or (body_text or "")[:500]
    from_email = _graph_single_address(msg.get("from"))
    to_json = _graph_recipient_list_graph(msg.get("toRecipients")) or None
    cc_json = _graph_recipient_list_graph(msg.get("ccRecipients")) or None
    bcc_json = _graph_recipient_list_graph(msg.get("bccRecipients")) or None
    sent_at = parse_graph_datetime(msg.get("sentDateTime"))
    received_at = parse_graph_datetime(msg.get("receivedDateTime")) or sent_at or datetime.now(timezone.utc)
    participants = participant_emails(from_email, to_json, cc_json, bcc_json)
    is_unread = msg.get("isRead") is False
    atts_raw = attachments or []
    norm_atts = [
        NormalizedAttachment(
            external_attachment_id=str(a.get("id")),
            filename=a.get("name"),
            mime_type=a.get("contentType"),
            size_bytes=int(a["size"]) if a.get("size") is not None else None,
            is_inline=bool(a.get("isInline") is True),
            provider_extra={"odata_type": a.get("@odata.type")},
        )
        for a in atts_raw
        if a.get("id")
    ]
    norm = NormalizedEmailMessage(
        tenant_id=tenant_id,
        mailbox_id=mailbox_id,
        provider=provider,
        external_message_id=ext_mid,
        external_thread_id=ext_thread,
        from_email=from_email,
        to_json=to_json,
        cc_json=cc_json,
        bcc_json=bcc_json,
        subject=subj,
        sent_at=sent_at,
        received_at=received_at,
        snippet=snippet or None,
        body_text=body_text,
        body_html=body_html,
        direction="inbound",
        is_unread=bool(is_unread),
        attachments=norm_atts,
    )
    rollup = NormalizedThreadRollup(
        external_thread_id=ext_thread,
        subject=subj,
        snippet=norm.snippet,
        participants_json=participants,
        last_message_at=received_at,
        message_count=None,
        unread_count=1 if is_unread else 0,
    )
    return rollup, norm
