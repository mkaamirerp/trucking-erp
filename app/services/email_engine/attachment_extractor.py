"""Download attachment bytes for extraction gates (Gmail today; Graph later)."""

from __future__ import annotations

import base64
from urllib.parse import quote

import httpx

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


async def download_gmail_attachment_bytes(
    access_token: str,
    gmail_message_id: str,
    attachment_id: str,
) -> bytes:
    mid = quote(gmail_message_id, safe="")
    aid = quote(attachment_id, safe="")
    url = f"{GMAIL_API_BASE}/messages/{mid}/attachments/{aid}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()
        data = resp.json().get("data")
        if not data:
            return b""
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8"))
