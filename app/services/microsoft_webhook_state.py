"""Signed clientState for Microsoft Graph subscriptions (tenant binding + webhook validation)."""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings


def _secret() -> str:
    return (settings.microsoft_webhook_client_state_secret or "") or settings.jwt_secret


def sign_ms_graph_client_state(tenant_id: int) -> str:
    """Compact clientState (<=128 chars for Graph). Format: tid:hexhmac"""
    tid = str(int(tenant_id))
    digest = hmac.new(_secret().encode("utf-8"), tid.encode("utf-8"), hashlib.sha256).hexdigest()[:20]
    return f"{tid}:{digest}"


def verify_ms_graph_client_state(client_state: str | None) -> int | None:
    if not client_state or ":" not in client_state:
        return None
    tid_s, sig = client_state.split(":", 1)
    if not tid_s.isdigit() or len(sig) < 16:
        return None
    try:
        tid = int(tid_s)
    except ValueError:
        return None
    expected = hmac.new(_secret().encode("utf-8"), tid_s.encode("utf-8"), hashlib.sha256).hexdigest()[:20]
    if not hmac.compare_digest(sig, expected):
        return None
    return tid
