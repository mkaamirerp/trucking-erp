"""Gmail users.watch / stop for Pub/Sub–driven delta ingestion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.tenant_email_account import TenantEmailAccount
from app.services.gmail_oauth import refresh_access_token
from app.utils.encryption import decrypt_secret

logger = logging.getLogger(__name__)

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


async def _http_watch(access_token: str, body: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GMAIL_API}/watch",
            json=body,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()
    return resp.json()


async def gmail_users_watch(
    access_token: str,
    *,
    topic_name: str,
    label_ids: tuple[str, ...] = ("INBOX",),
) -> tuple[str | None, datetime | None]:
    """
    Call users.watch. Returns (historyId str or None, expiration UTC).
    Gmail returns expiration as Unix ms in the JSON string field \"expiration\".
    """
    payload: dict[str, Any] = {"topicName": topic_name, "labelIds": list(label_ids)}
    data = await _http_watch(access_token, payload)
    hid = str(data.get("historyId") or "").strip() or None
    exp_raw = data.get("expiration")
    exp_dt: datetime | None = None
    if exp_raw is not None:
        try:
            exp_ms = int(exp_raw)
            exp_dt = datetime.fromtimestamp(exp_ms / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError):
            logger.warning("gmail watch: could not parse expiration %r", exp_raw)
    return hid, exp_dt


async def gmail_users_stop(access_token: str) -> None:
    """Best-effort users.stop (clears push subscription for this account)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GMAIL_API}/stop",
            headers={"Authorization": f"Bearer {access_token}"},
            content=b"",
        )
    if resp.status_code == 404:
        return
    if resp.status_code not in (200, 204):
        resp.raise_for_status()


async def register_or_renew_gmail_watch_for_tenant(
    tenant_db: AsyncSession,
    tenant_id: int,
    *,
    topic_name: str | None = None,
) -> dict[str, Any]:
    """
    Refresh OAuth, POST users.watch, persist gmail_watch_expiration_at and clear last_error on success.
    """
    topic = topic_name or getattr(settings, "gmail_pubsub_topic_name", None)
    if not topic or not str(topic).strip():
        raise ValueError("gmail_pubsub_topic_name is not configured")

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

    hid, exp_dt = await gmail_users_watch(access_token, topic_name=str(topic).strip())
    acc.gmail_watch_expiration_at = exp_dt
    acc.updated_at = datetime.now(timezone.utc)
    if acc.last_error and str(acc.last_error).startswith("watch_failed:"):
        acc.last_error = None
    await tenant_db.commit()
    return {
        "ok": True,
        "historyId": hid,
        "gmail_watch_expires_at": exp_dt.isoformat() if exp_dt else None,
    }


async def stop_gmail_watch_for_tenant(tenant_db: AsyncSession, tenant_id: int) -> None:
    """Call users.stop using stored refresh token; clear local watch expiration."""
    acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if not acc:
        return
    try:
        refresh_token = decrypt_secret(acc.refresh_token_encrypted).decode("utf-8")
        tok = await refresh_access_token(refresh_token)
        access_token = tok.get("access_token")
        if access_token:
            await gmail_users_stop(access_token)
    except Exception as exc:
        logger.warning("gmail users.stop failed tenant_id=%s: %s", tenant_id, exc)
    acc.gmail_watch_expiration_at = None
    acc.updated_at = datetime.now(timezone.utc)
    await tenant_db.flush()
