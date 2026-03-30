"""Cloudflare Turnstile siteverify (optional; used after login password failure streaks)."""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TURNSTILE_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile_token(token: str | None) -> bool:
    secret = (settings.turnstile_secret_key or "").strip()
    if not secret:
        return False
    t = (token or "").strip()
    if not t:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                TURNSTILE_SITEVERIFY_URL,
                data={"secret": secret, "response": t},
            )
            r.raise_for_status()
            body = r.json()
    except Exception as exc:
        logger.warning("turnstile_siteverify_error err=%s", exc)
        return False
    return bool(body.get("success"))
