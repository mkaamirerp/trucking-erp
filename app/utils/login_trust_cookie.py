"""
Signed httpOnly cookie marking a browser as familiar for a tenant (UX / risk signal only).
Does not replace password or OTP. No server-side device registry in v1.

Signing uses LOGIN_TRUST_COOKIE_SECRET only in production-grade environments.
jwt_secret is never used as a silent fallback in production or staging.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

from fastapi import Request, Response

from app.core.config import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "trk_login_trust"
LOGIN_TRUST_PAYLOAD_VERSION = 1
# 90 days; sliding refresh on each successful login.
LOGIN_TRUST_COOKIE_MAX_AGE = 90 * 24 * 3600


def _trust_signing_key_bytes() -> bytes | None:
    """
    Effective HMAC key for trk_login_trust. Returns None if the feature is disabled (fail closed).
    Production/staging: only login_trust_cookie_secret (non-empty).
    Dev-like: secret OR (explicit dev flag + jwt_secret).
    """
    direct = (settings.login_trust_cookie_secret or "").strip()
    if direct:
        return direct.encode("utf-8")

    if settings.is_production():
        return None
    e = (settings.environment or "").lower()
    if e in ("staging", "stage", "stg", "preprod"):
        return None

    if settings.login_trust_cookie_dev_fallback_to_jwt and (settings.jwt_secret or "").strip():
        return (settings.jwt_secret or "").encode("utf-8")

    return None


def _trust_cookie_params(*, max_age: int) -> dict[str, Any]:
    secure = bool(settings.secure_cookies)
    domain = settings.cookie_domain or (f".{settings.base_domain}" if settings.base_domain else None)
    out: dict[str, Any] = {
        "path": "/",
        "httponly": True,
        "secure": secure,
        "samesite": settings.jwt_same_site,
        "max_age": max_age,
    }
    if domain:
        out["domain"] = domain
    return out


def _b64url_decode(s: str) -> bytes:
    pad = (-len(s)) % 4
    return base64.urlsafe_b64decode(s + ("=" * pad))


def _sign_payload_b64(payload_b64: str, key: bytes) -> str:
    return hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def create_login_trust_cookie_value(tenant_id: int) -> str | None:
    key = _trust_signing_key_bytes()
    if not key:
        return None
    now = int(time.time())
    body = {"t": int(tenant_id), "exp": now + LOGIN_TRUST_COOKIE_MAX_AGE, "v": LOGIN_TRUST_PAYLOAD_VERSION}
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = _sign_payload_b64(payload_b64, key)
    return f"{payload_b64}.{sig}"


def verify_login_trust_cookie(request: Request, tenant_id: int) -> bool:
    """True if the cookie is present, correctly signed with the effective key, matches tenant_id, and not expired."""
    key = _trust_signing_key_bytes()
    if not key:
        return False
    raw = request.cookies.get(COOKIE_NAME)
    if not raw or "." not in raw:
        return False
    payload_b64, sig = raw.rsplit(".", 1)
    if len(sig) != 64:
        return False
    if not hmac.compare_digest(_sign_payload_b64(payload_b64, key), sig):
        return False
    try:
        body = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return False
    if body.get("v") != LOGIN_TRUST_PAYLOAD_VERSION:
        return False
    if int(body.get("t", -1)) != int(tenant_id):
        return False
    exp = int(body.get("exp", 0))
    if exp <= int(time.time()):
        return False
    return True


def set_login_trust_cookie(response: Response, tenant_id: int) -> None:
    val = create_login_trust_cookie_value(tenant_id)
    if not val:
        logger.debug(
            "event=login_trust_cookie_skip reason=no_signing_key tenant_id=%s env=%s",
            int(tenant_id),
            settings.environment,
        )
        return
    response.set_cookie(
        COOKIE_NAME,
        val,
        **_trust_cookie_params(max_age=LOGIN_TRUST_COOKIE_MAX_AGE),
    )


def clear_login_trust_cookie(response: Response) -> None:
    params = _trust_cookie_params(max_age=0)
    params["max_age"] = 0
    params["expires"] = 0
    response.set_cookie(COOKIE_NAME, "", **params)
