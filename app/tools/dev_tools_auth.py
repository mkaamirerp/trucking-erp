"""
Temporary dev-only auth for /api/v1/tools. Simple password + signed cookie.
No RBAC, no DB, no SSM required. Will be removed later.
"""
from __future__ import annotations

import hmac
import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request
from fastapi import HTTPException

COOKIE_NAME = "truckerp_tools_unlocked"

# Simple default — no env required. Override with TOOLS_DEV_PASSWORD / TOOLS_DEV_SECRET if you want.
DEFAULT_PASSWORD = "devtools123"
DEFAULT_SECRET = "devtools-secret-123"


def _get_secret() -> str:
    v = os.environ.get("TOOLS_DEV_SECRET")
    return v.strip() if v and str(v).strip() else DEFAULT_SECRET


def _get_password() -> str:
    v = os.environ.get("TOOLS_DEV_PASSWORD")
    if v is not None and (not isinstance(v, str) or v.strip()):
        return v.strip() if isinstance(v, str) else str(v)
    return DEFAULT_PASSWORD


def _get_max_age() -> int:
    return int(os.environ.get("TOOLS_DEV_MAX_AGE_SECONDS", "3600"))


def verify_tools_password(password: str) -> bool:
    return hmac.compare_digest(password, _get_password())


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_get_secret(), salt="dev-tools")


def make_cookie_value() -> str:
    return _serializer().dumps("unlocked")


def require_tools_unlocked(request: Request) -> None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=401, detail="TOOLS_LOCKED")
    try:
        _serializer().loads(raw, max_age=_get_max_age())
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="TOOLS_LOCKED")
