"""Microsoft Graph change notification endpoint (validation + lifecycle)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.deps.tenant_db import open_tenant_session_by_id
from app.models.tenant_email_account import TenantEmailAccount
from app.services.microsoft_graph_sync import PROVIDER_MICROSOFT365, sync_microsoft_delta_for_tenant
from app.services.microsoft_webhook_state import verify_ms_graph_client_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["microsoft_graph_webhook"])


@router.api_route("/webhooks/microsoft-graph", methods=["GET", "POST"])
async def microsoft_graph_notification(request: Request):
    """
    Graph subscription validation: return `validationToken` as text/plain 200.
    Notifications: verify clientState → tenant; match subscription id; delta sync.
    """
    vt = request.query_params.get("validationToken")
    if vt:
        return PlainTextResponse(content=vt, status_code=200)

    if request.method.upper() == "GET":
        return PlainTextResponse(content="", status_code=200)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

    if not isinstance(body, dict):
        return {"ok": True, "skipped": "not_object"}

    for note in body.get("value") or []:
        if not isinstance(note, dict):
            continue
        cs = note.get("clientState")
        tid = verify_ms_graph_client_state(str(cs) if cs is not None else None)
        if tid is None:
            logger.info("microsoft webhook: bad clientState")
            continue
        sub_id = str(note.get("subscriptionId") or "").strip()
        if not sub_id:
            continue
        try:
            async for tenant_db in open_tenant_session_by_id(int(tid)):
                acc = await tenant_db.scalar(
                    select(TenantEmailAccount)
                    .where(
                        TenantEmailAccount.tenant_id == int(tid),
                        TenantEmailAccount.provider == PROVIDER_MICROSOFT365,
                        TenantEmailAccount.ms_graph_subscription_id == sub_id,
                    )
                    .limit(1)
                )
                if not acc:
                    logger.warning(
                        "microsoft webhook: subscription %s not found for tenant %s", sub_id, tid
                    )
                    break
                acc.ms_graph_last_notification_at = datetime.now(timezone.utc)
                await tenant_db.commit()
                break
            async for tenant_db in open_tenant_session_by_id(int(tid)):
                try:
                    await sync_microsoft_delta_for_tenant(tenant_db, int(tid), max_pages=15)
                except Exception as exc:
                    logger.warning("microsoft delta sync failed tenant=%s: %s", tid, exc)
                break
        except Exception as exc:
            logger.warning("microsoft webhook processing failed: %s", exc)

    return {"ok": True}
