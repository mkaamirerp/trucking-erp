"""Google Cloud Pub/Sub push target for Gmail mailbox notifications (platform URL, no tenant Host).

Primary production ingestion: Gmail watch → Pub/Sub → this route → delta sync → persist → intake routing.
Manual admin/inbox sync endpoints must call the same delta sync; do not depend on UI clicks for correctness.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.tenant_email_account import TenantEmailAccount
from app.services.email_ingestion_gmail import decode_pubsub_gmail_notification, sync_gmail_delta_for_tenant
from app.services.gmail_mailbox_platform_index import resolve_tenant_id_for_gmail_address
from app.services.gmail_pubsub_auth import verify_pubsub_push_oidc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gmail_pubsub"])


def _require_push_auth(request: Request) -> None:
    """
    Anonymous push is never allowed: set OIDC audience (standard Pub/Sub → HTTPS) and/or
    GMAIL_PUBSUB_PUSH_TOKEN (X-TruckERP-Gmail-Push-Token) for lab/custom forwarders.
    Pub/Sub OIDC pushes do not include custom headers; verified Bearer is sufficient on the OIDC path.
    """
    aud = getattr(settings, "gmail_pubsub_push_audience", None)
    shared = getattr(settings, "gmail_pubsub_push_token", None)
    aud_ok = bool(aud and str(aud).strip())
    shared_ok = bool(shared and str(shared).strip())

    if not aud_ok and not shared_ok:
        raise HTTPException(
            status_code=503,
            detail="Gmail Pub/Sub push auth is not configured: set GMAIL_PUBSUB_PUSH_AUDIENCE (OIDC) and/or GMAIL_PUBSUB_PUSH_TOKEN",
        )

    auth_hdr = request.headers.get("Authorization") or ""
    bearer = auth_hdr[7:].strip() if auth_hdr.startswith("Bearer ") else None

    if aud_ok:
        if not bearer:
            raise HTTPException(status_code=401, detail="Missing Authorization bearer (OIDC required)")
        try:
            verify_pubsub_push_oidc(bearer, aud.strip())
        except ValueError as exc:
            logger.warning("gmail_pubsub_push: OIDC verify failed: %s", exc)
            raise HTTPException(status_code=401, detail="Invalid OIDC token") from exc
        return

    if request.headers.get("X-TruckERP-Gmail-Push-Token") != shared:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/webhooks/gmail/pubsub")
async def gmail_pubsub_push(request: Request) -> dict:
    """
    Primary wake-up path: Pub/Sub push → delta Gmail sync (History) → persist → intake routing.
    Returns 200 JSON on parse success so Pub/Sub does not retry indefinitely on business logic skips.
    """
    _require_push_auth(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

    email, _hist = decode_pubsub_gmail_notification(body if isinstance(body, dict) else {})
    if not email:
        logger.info("gmail_pubsub_push: no email in payload; ack")
        return {"ok": True, "skipped": "no_email"}

    async with AsyncSessionLocal() as platform_db:
        tenant_id = await resolve_tenant_id_for_gmail_address(platform_db, email)

    if not tenant_id:
        logger.info("gmail_pubsub_push: no tenant mapping for %s; ack", email[:3] + "***")
        return {"ok": True, "skipped": "unknown_mailbox"}

    try:
        async for tenant_db in open_tenant_session_by_id(int(tenant_id)):
            acc = await tenant_db.scalar(
                select(TenantEmailAccount).where(
                    TenantEmailAccount.tenant_id == int(tenant_id),
                    TenantEmailAccount.provider == "gmail",
                ).limit(1)
            )
            if acc:
                acc.last_gmail_webhook_at = datetime.now(timezone.utc)
                await tenant_db.commit()
            await sync_gmail_delta_for_tenant(tenant_db, int(tenant_id))
            break
    except Exception as exc:
        logger.exception("gmail_pubsub_push sync failed tenant_id=%s: %s", tenant_id, exc)
        return {"ok": True, "error": "sync_failed"}

    return {"ok": True, "tenant_id": tenant_id}
