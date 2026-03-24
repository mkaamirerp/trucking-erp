"""Gmail OAuth 2.0 flow: authorize URL, token exchange, userinfo."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from urllib.parse import urlencode

import httpx

from app.core.config import settings

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _state_secret() -> str:
    return (settings.google_client_secret or "") or settings.jwt_secret


def build_authorize_url(redirect_uri: str, state: str) -> str:
    """Build Google OAuth authorize URL. Fails if client_id not configured."""
    client_id = settings.google_client_id
    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def make_state(tenant_id: int, tenant_slug: str) -> str:
    """Create signed state for CSRF. Payload: tenant_id.tenant_slug.nonce. Return target derived from slug."""
    nonce = secrets.token_urlsafe(16)
    payload = f"{tenant_id}.{tenant_slug}.{nonce}"
    sig = hmac.new(
        _state_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{sig}"


def parse_state(state: str) -> tuple[int, str] | None:
    """Parse and verify signed state. Returns (tenant_id, tenant_slug) or None."""
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
    segments = payload.split(".", 2)  # tenant_id, tenant_slug, nonce
    if len(segments) != 3:
        return None
    try:
        return (int(segments[0]), segments[1])
    except ValueError:
        return None


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for access and refresh tokens."""
    client_id = settings.google_client_id
    client_secret = settings.google_client_secret
    if not client_id or not client_secret:
        raise ValueError("Google OAuth credentials not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def get_google_userinfo(access_token: str) -> dict:
    """Fetch Google OAuth2 userinfo (email, id, verified_email, etc.)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()
    return resp.json()


async def get_user_email(access_token: str) -> str:
    """Fetch user email from Google userinfo."""
    data = await get_google_userinfo(access_token)
    return data.get("email", "")


async def refresh_access_token(refresh_token: str) -> dict:
    """Exchange refresh token for new access token."""
    client_id = settings.google_client_id
    client_secret = settings.google_client_secret
    if not client_id or not client_secret:
        raise ValueError("Google OAuth credentials not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()
