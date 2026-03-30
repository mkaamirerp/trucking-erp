from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import jwt
from fastapi import HTTPException, Request, status

from app.core.config import settings


class TokenType:
    ACCESS = "access"
    REFRESH = "refresh"
    LOGIN_STEP_UP_PROOF = "login_step_up_proof"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_secret() -> str:
    return settings.jwt_secret or os.getenv("JWT_SECRET") or "dev-change-me"


def _encode_token(
    *,
    token_type: str,
    user_id: str | int,
    tenant_id: int,
    tenant_slug: str | None,
    roles: list[str] | None,
    sv: int,
    expires_in: timedelta,
) -> str:
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": tenant_id,
        "tenant_slug": tenant_slug,
        "roles": roles or [],
        "type": token_type,
        "sv": int(sv),
        "iat": int(_utcnow().timestamp()),
        "exp": int((_utcnow() + expires_in).timestamp()),
    }
    return jwt.encode(payload, _default_secret(), algorithm=settings.jwt_algorithm)


def create_access_token(
    *, user_id: str | int, tenant_id: int, tenant_slug: str | None, roles: list[str] | None, sv: int
) -> str:
    return _encode_token(
        token_type=TokenType.ACCESS,
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        roles=roles,
        sv=sv,
        expires_in=timedelta(minutes=settings.jwt_access_minutes),
    )


def create_refresh_token(
    *, user_id: str | int, tenant_id: int, tenant_slug: str | None, roles: list[str] | None, sv: int
) -> str:
    return _encode_token(
        token_type=TokenType.REFRESH,
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        roles=roles,
        sv=sv,
        expires_in=timedelta(days=settings.jwt_refresh_days),
    )


def create_login_step_up_proof_token(*, tenant_id: int, email_norm: str, otp_row_id: int) -> str:
    """Short-lived proof returned after login step-up OTP verify; must match tenant + email at login."""
    now = _utcnow()
    payload: Dict[str, Any] = {
        "type": TokenType.LOGIN_STEP_UP_PROOF,
        "tenant_id": int(tenant_id),
        "email_norm": email_norm,
        "otp_id": int(otp_row_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, _default_secret(), algorithm=settings.jwt_algorithm)


def decode_login_step_up_proof_token(token: str | None) -> dict | None:
    """Returns payload dict or None if missing/invalid/expired/wrong type."""
    if not token or not _looks_like_jwt(token):
        return None
    try:
        payload = jwt.decode(token, _default_secret(), algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != TokenType.LOGIN_STEP_UP_PROOF:
        return None
    return payload


def extract_sv(payload: dict) -> int | None:
    v = payload.get("sv")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _looks_like_jwt(raw: str) -> bool:
    """True if the string has the form header.payload.signature (three base64 segments)."""
    if not raw or not isinstance(raw, str):
        return False
    parts = raw.split(".")
    return len(parts) == 3 and all(len(p) > 0 for p in parts)


def decode_token(token: str, *, expected_type: str | None = None) -> dict:
    if not _looks_like_jwt(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")
    try:
        payload = jwt.decode(token, _default_secret(), algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


def get_token_from_request(request: Request, *, prefer_refresh: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (token, token_type_claim) if present in Authorization header or cookies.
    """
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            return token, payload.get("type")
        except HTTPException:
            raise
    # Cookies
    cookie_token = None
    if prefer_refresh:
        cookie_token = request.cookies.get("refresh_token") or request.cookies.get("access_token")
    else:
        cookie_token = request.cookies.get("access_token") or request.cookies.get("refresh_token")
    if cookie_token:
        payload = decode_token(cookie_token)
        return cookie_token, payload.get("type")
    return None, None
