"""Microsoft 365 mail: delta sync + subscription lifecycle; uses shared email ingestion engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.tenant_email_account import TenantEmailAccount
from app.services.email_engine.email_ingestion_engine import IngestionContext, ingest_normalized_thread
from app.services.email_engine.message_normalizer import graph_api_message_to_normalized
from app.services.email_providers.microsoft365_adapter import (
    graph_create_subscription,
    graph_delete_subscription,
    graph_delta_get,
    graph_get_message,
    graph_list_attachments,
    graph_renew_subscription,
    inbox_delta_start_url,
)
from app.services.microsoft_oauth import refresh_ms_access_token
from app.services.microsoft_webhook_state import sign_ms_graph_client_state
from app.utils.encryption import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

PROVIDER_MICROSOFT365 = "microsoft365"


@dataclass
class MicrosoftSyncResult:
    tenant_id: int
    provider: str
    messages_processed: int
    delta_pages: int
    delta_cursor_advanced: bool


async def _access_token_for_account(acc: TenantEmailAccount) -> str:
    refresh = decrypt_secret(acc.refresh_token_encrypted).decode("utf-8")
    tok = await refresh_ms_access_token(refresh_token=refresh)
    access = tok.get("access_token")
    if not access:
        raise ValueError("Microsoft token refresh returned no access_token")
    new_refresh = tok.get("refresh_token")
    if new_refresh:
        acc.refresh_token_encrypted = encrypt_secret(new_refresh)
    exp = tok.get("expires_in")
    if exp is not None and isinstance(exp, (int, float)):
        from datetime import timedelta

        acc.token_expiry_at = datetime.now(timezone.utc) + timedelta(seconds=int(exp))
    acc.access_token_encrypted = encrypt_secret(access)
    acc.updated_at = datetime.now(timezone.utc)
    return access


async def ensure_microsoft_subscription(
    tenant_db: AsyncSession,
    tenant_id: int,
    acc: TenantEmailAccount,
    *,
    access_token: str | None = None,
) -> None:
    """Create or confirm Graph subscription for inbox messages."""
    notif_url = (getattr(settings, "microsoft_webhook_notification_url", None) or "").strip()
    if not notif_url:
        acc.ms_graph_subscription_status = "skipped_no_notification_url"
        acc.ms_graph_last_sync_error = "MICROSOFT_WEBHOOK_NOTIFICATION_URL not configured"
        return
    token = access_token or (await _access_token_for_account(acc))
    old_sid = (acc.ms_graph_subscription_id or "").strip()
    if old_sid:
        try:
            await graph_delete_subscription(token, old_sid)
        except Exception as exc:
            logger.warning("microsoft graph delete prior subscription: %s", exc)
    cs = sign_ms_graph_client_state(tenant_id)
    sub = await graph_create_subscription(token, notification_url=notif_url, client_state=cs)
    sid = str(sub.get("id") or "")
    exp_raw = sub.get("expirationDateTime")
    exp_dt = None
    if isinstance(exp_raw, str):
        try:
            s = exp_raw.replace("Z", "+00:00") if exp_raw.endswith("Z") else exp_raw
            exp_dt = datetime.fromisoformat(s)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        except Exception:
            exp_dt = None
    acc.ms_graph_subscription_id = sid or None
    acc.ms_graph_subscription_status = "active" if sid else "error"
    acc.ms_graph_subscription_expiration_at = exp_dt
    acc.ms_graph_last_sync_error = None if sid else "subscription_create_no_id"


async def stop_microsoft_subscription_safe(
    tenant_db: AsyncSession,
    acc: TenantEmailAccount,
) -> None:
    sub_id = (acc.ms_graph_subscription_id or "").strip()
    if not sub_id:
        return
    try:
        access = await _access_token_for_account(acc)
        await graph_delete_subscription(access, sub_id)
    except Exception as exc:
        logger.warning("microsoft graph subscription delete failed: %s", exc)
    acc.ms_graph_subscription_id = None
    acc.ms_graph_subscription_status = "disconnected"
    acc.ms_graph_subscription_expiration_at = None
    acc.ms_graph_delta_link = None
    acc.updated_at = datetime.now(timezone.utc)


async def renew_microsoft_subscription_if_due(
    tenant_db: AsyncSession,
    tenant_id: int,
    acc: TenantEmailAccount,
    *,
    renew_within_hours: int = 12,
    force: bool = False,
) -> bool:
    """POST-less renewal used by cron/admin; returns True if renewed."""
    sub_id = (acc.ms_graph_subscription_id or "").strip()
    exp = acc.ms_graph_subscription_expiration_at
    if not sub_id:
        return False
    if not force and not exp:
        return False
    now = datetime.now(timezone.utc)
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if not force and exp and (exp - now).total_seconds() > renew_within_hours * 3600:
        return False
    access = await _access_token_for_account(acc)
    sub = await graph_renew_subscription(access, sub_id)
    exp_raw = sub.get("expirationDateTime")
    if isinstance(exp_raw, str):
        try:
            s = exp_raw.replace("Z", "+00:00") if exp_raw.endswith("Z") else exp_raw
            new_exp = datetime.fromisoformat(s)
            if new_exp.tzinfo is None:
                new_exp = new_exp.replace(tzinfo=timezone.utc)
            acc.ms_graph_subscription_expiration_at = new_exp
        except Exception:
            pass
    acc.ms_graph_subscription_status = "active"
    acc.updated_at = datetime.now(timezone.utc)
    await tenant_db.commit()
    return True


async def sync_microsoft_delta_for_tenant(
    tenant_db: AsyncSession,
    tenant_id: int,
    *,
    max_pages: int = 25,
    top: int = 50,
) -> MicrosoftSyncResult:
    """Apply Graph delta for primary Microsoft 365 mailbox; ingest via shared engine (review-only path)."""
    acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(
            TenantEmailAccount.tenant_id == tenant_id,
            TenantEmailAccount.provider == PROVIDER_MICROSOFT365,
        )
        .limit(1)
    )
    if not acc:
        raise ValueError("No Microsoft 365 account for tenant")

    now = datetime.now(timezone.utc)
    msgs = 0
    pages = 0
    new_delta: str | None = None

    try:
        access = await _access_token_for_account(acc)
        url: str | None = (acc.ms_graph_delta_link or "").strip() or inbox_delta_start_url(top=top)
        while url and pages < max_pages:
            page = await graph_delta_get(access, url)
            pages += 1
            for item in page.get("value") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("@removed"):
                    continue
                mid = str(item.get("id") or "").strip()
                if not mid:
                    continue
                full = await graph_get_message(access, mid)
                atts: list[dict] = []
                if full.get("hasAttachments"):
                    atts = await graph_list_attachments(access, mid)
                rollup, norm = graph_api_message_to_normalized(
                    tenant_id,
                    acc.id,
                    PROVIDER_MICROSOFT365,
                    full,
                    attachments=atts,
                )
                ctx = IngestionContext(
                    tenant_id=tenant_id,
                    provider=PROVIDER_MICROSOFT365,
                    gmail_access_token=None,
                )
                await ingest_normalized_thread(tenant_db, ctx, rollup, [norm])
                msgs += 1
            next_link = page.get("@odata.nextLink")
            delta_link = page.get("@odata.deltaLink")
            if delta_link:
                new_delta = str(delta_link)
            url = next_link if next_link else None

        if new_delta:
            acc.ms_graph_delta_link = new_delta
        acc.ms_graph_last_delta_sync_at = now
        acc.ms_graph_last_sync_status = "ok"
        acc.ms_graph_last_sync_error = None
        acc.last_sync_at = now
        acc.last_error = None
        await tenant_db.commit()
        return MicrosoftSyncResult(
            tenant_id=tenant_id,
            provider=PROVIDER_MICROSOFT365,
            messages_processed=msgs,
            delta_pages=pages,
            delta_cursor_advanced=bool(new_delta),
        )
    except Exception as exc:
        acc.ms_graph_last_delta_sync_at = now
        acc.ms_graph_last_sync_status = "error"
        acc.ms_graph_last_sync_error = (str(exc) or "delta_sync_failed")[:2000]
        acc.last_error = acc.ms_graph_last_sync_error
        await tenant_db.commit()
        raise
