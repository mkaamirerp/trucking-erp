"""
Microsoft 365 Graph adapter: HTTP only — fetch subscriptions, messages, attachments, delta pages.
Normalization and ingestion: `email_engine` + `microsoft_graph_sync`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


async def graph_http_json(
    access_token: str,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.request(method.upper(), url, headers=headers, json=json_body)
    if resp.status_code >= 400:
        resp.raise_for_status()
    if resp.status_code == 204:
        return resp.status_code, None
    try:
        data = resp.json()
    except Exception:
        data = None
    return resp.status_code, data


async def graph_get_message(access_token: str, message_id: str) -> dict[str, Any]:
    mid = quote(message_id, safe="")
    url = f"{GRAPH_ROOT}/me/messages/{mid}"
    _, data = await graph_http_json(access_token, "GET", url)
    if not isinstance(data, dict):
        raise RuntimeError("Graph message response invalid")
    return data


async def graph_list_attachments(access_token: str, message_id: str) -> list[dict[str, Any]]:
    mid = quote(message_id, safe="")
    url = f"{GRAPH_ROOT}/me/messages/{mid}/attachments"
    out: list[dict[str, Any]] = []
    while url:
        _, data = await graph_http_json(access_token, "GET", url)
        if not isinstance(data, dict):
            break
        for a in data.get("value") or []:
            if isinstance(a, dict) and a.get("id"):
                out.append(a)
        url = data.get("@odata.nextLink")
    return out


async def graph_delta_get(access_token: str, delta_url: str) -> dict[str, Any]:
    _, data = await graph_http_json(access_token, "GET", delta_url)
    if not isinstance(data, dict):
        raise RuntimeError("Graph delta response invalid")
    return data


def inbox_delta_start_url(*, top: int = 50) -> str:
    return f"{GRAPH_ROOT}/me/mailFolders/inbox/messages/delta?$top={int(top)}"


def subscription_expiration_utc(*, hours: int = 70) -> str:
    """Graph allows up to ~4230 min for outlook resources; stay under with 70h default."""
    exp = datetime.now(timezone.utc) + timedelta(hours=hours)
    return exp.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")


async def graph_create_subscription(
    access_token: str,
    *,
    notification_url: str,
    client_state: str,
    resource: str = "me/mailFolders('inbox')/messages",
) -> dict[str, Any]:
    body = {
        "changeType": "created,updated",
        "notificationUrl": notification_url,
        "resource": resource,
        "expirationDateTime": subscription_expiration_utc(hours=70),
        "clientState": client_state[:128],
    }
    _, data = await graph_http_json(access_token, "POST", f"{GRAPH_ROOT}/subscriptions", json_body=body)
    if not isinstance(data, dict):
        raise RuntimeError("Graph subscription create failed")
    return data


async def graph_renew_subscription(access_token: str, subscription_id: str) -> dict[str, Any]:
    sid = quote(subscription_id, safe="")
    body = {"expirationDateTime": subscription_expiration_utc(hours=70)}
    _, data = await graph_http_json(
        access_token,
        "PATCH",
        f"{GRAPH_ROOT}/subscriptions/{sid}",
        json_body=body,
    )
    if not isinstance(data, dict):
        raise RuntimeError("Graph subscription renew failed")
    return data


async def graph_delete_subscription(access_token: str, subscription_id: str) -> None:
    sid = quote(subscription_id, safe="")
    await graph_http_json(access_token, "DELETE", f"{GRAPH_ROOT}/subscriptions/{sid}")
