"""Microsoft 365 OAuth 2.0 (v2 endpoint): authorize URL, token exchange, refresh."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from urllib.parse import urlencode

import httpx

from app.core.config import settings

MS_SCOPES = ["offline_access", "Mail.Read", "User.Read", "openid", "profile"]


def _state_secret() -> str:
    return (settings.microsoft_client_secret or "") or settings.jwt_secret


def authority_token_url() -> str:
    tid = (settings.microsoft_authority_tenant or "common").strip()
    return f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token"


def authority_authorize_url() -> str:
    tid = (settings.microsoft_authority_tenant or "common").strip()
    return f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/authorize"


def build_microsoft_authorize_url(*, redirect_uri: str, state: str) -> str:
    cid = settings.microsoft_client_id
    if not cid:
        raise ValueError("MICROSOFT_CLIENT_ID is not configured")
    params = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(MS_SCOPES),
        "state": state,
        "prompt": "consent",
    }
    return f"{authority_authorize_url()}?{urlencode(params)}"


def make_ms_state(tenant_id: int, tenant_slug: str) -> str:
    nonce = secrets.token_urlsafe(16)
    payload = f"{tenant_id}.{tenant_slug}.{nonce}"
    sig = hmac.new(
        _state_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{sig}"


def parse_ms_state(state: str) -> tuple[int, str] | None:
    parts = state.rsplit(".", 1)
    if len(parts) != 2:
        return None
    payload, sig = parts
    expected = hmac.new(
        _state_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    segments = payload.split(".", 2)
    if len(segments) != 3:
        return None
    try:
        return (int(segments[0]), segments[1])
    except ValueError:
        return None


async def exchange_ms_code_for_tokens(*, code: str, redirect_uri: str) -> dict:
    cid = settings.microsoft_client_id
    secret = settings.microsoft_client_secret
    if not cid or not secret:
        raise ValueError("Microsoft OAuth credentials not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            authority_token_url(),
            data={
                "client_id": cid,
                "client_secret": secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def refresh_ms_access_token(*, refresh_token: str) -> dict:
    cid = settings.microsoft_client_id
    secret = settings.microsoft_client_secret
    if not cid or not secret:
        raise ValueError("Microsoft OAuth credentials not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            authority_token_url(),
            data={
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def graph_get_me_profile(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            params={"$select": "id,mail,userPrincipalName,displayName"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()
    return resp.json()
