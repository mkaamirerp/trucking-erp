"""
In-memory rate limiting for selected public endpoints (verify-otp, resend-otp, forgot-password, login).

Limits are per IP and per identity (signup_id or email-hash, or tenant+email-hash for login) to prevent
brute-force and abuse. Uses a simple sliding-window counter; safe for single-instance deployment.
For multi-instance, use Redis or similar in front.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import defaultdict
from fastapi import Request


def _email_hash(email: str) -> str:
    """Stable hash for rate-limit key; avoids storing raw email."""
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()[:16]


def _phone_fingerprint_hash(digits: str) -> str:
    d = re.sub(r"\D", "", digits or "")
    if not d:
        return "empty"
    return hashlib.sha256(d.encode("utf-8")).hexdigest()[:16]


class SlidingWindowLimiter:
    """Per-key sliding window: allow up to `max_requests` in `window_seconds`."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _clean(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._timestamps[key] = [t for t in self._timestamps[key] if t > cutoff]

    def allow(self, key: str) -> bool:
        """Return True if request is allowed, False if rate limited."""
        now = time.monotonic()
        with self._lock:
            self._clean(key, now)
            if len(self._timestamps[key]) >= self.max_requests:
                return False
            self._timestamps[key].append(now)
            return True


# Per-IP limits (shared by verify and resend)
verify_otp_per_ip = SlidingWindowLimiter(max_requests=15, window_seconds=900)   # 15 per 15 min
resend_otp_per_ip = SlidingWindowLimiter(max_requests=5, window_seconds=900)   # 5 per 15 min

# Per-identity limits (signup_id or email-hash)
verify_otp_per_identity = SlidingWindowLimiter(max_requests=20, window_seconds=900)  # 20 per 15 min
resend_otp_per_identity = SlidingWindowLimiter(max_requests=3, window_seconds=300)     # 3 per 5 min

# Forgot-password: per IP and per email to prevent abuse
forgot_password_per_ip = SlidingWindowLimiter(max_requests=5, window_seconds=900)      # 5 per 15 min per IP
forgot_password_per_email = SlidingWindowLimiter(max_requests=3, window_seconds=3600)  # 3 per hour per email

create_workspace_per_ip = SlidingWindowLimiter(max_requests=10, window_seconds=3600)  # 10 per hour per IP
create_workspace_per_user = SlidingWindowLimiter(max_requests=5, window_seconds=86400)  # 5 per day per user

# Login: per IP (same window density as verify_otp per IP) + per workspace identity (tenant + hashed email)
login_per_ip = SlidingWindowLimiter(max_requests=15, window_seconds=900)  # 15 per 15 min per IP
login_per_tenant_email = SlidingWindowLimiter(max_requests=10, window_seconds=3600)  # 10 per hour per tenant+email

# Public workspace intake (landing): cheap, abuse-resistant
workspace_intake_submit_per_ip = SlidingWindowLimiter(max_requests=30, window_seconds=3600)  # per hour
workspace_intake_submit_per_email = SlidingWindowLimiter(max_requests=5, window_seconds=86400)  # per day
workspace_intake_submit_per_phone = SlidingWindowLimiter(max_requests=8, window_seconds=86400)  # per day (digits hash)
workspace_intake_consume_per_ip = SlidingWindowLimiter(max_requests=60, window_seconds=900)  # per 15 min


def _client_ip(request: Request) -> str:
    return (request.client.host if request.client else "unknown") or "unknown"


def _identity_key(signup_id: str | None, email: str | None) -> str:
    """Single key for rate limiting by signup or email (hashed)."""
    if signup_id:
        return f"signup:{signup_id}"
    if email:
        return f"email:{_email_hash(email)}"
    return "anon"


async def rate_limit_verify_otp(request: Request) -> None:
    """Dependency: raises 429 if verify-otp is rate limited (per IP + per signup_id/email)."""
    ip = _client_ip(request)
    # We need identity from body; dependency runs before body is parsed in path. So we check IP only here,
    # and identity check is done inside the endpoint after parsing body. Alternatively we could use a
    # middleware that parses body for specific paths. Simplest: check IP in dependency; in endpoint we
    # check identity limit after we have payload. So this dependency only does IP.
    if not verify_otp_per_ip.allow(f"verify_ip:{ip}"):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


async def rate_limit_resend_otp(request: Request) -> None:
    """Dependency: raises 429 if resend-otp is rate limited (per IP). Identity limit in endpoint."""
    ip = _client_ip(request)
    if not resend_otp_per_ip.allow(f"resend_ip:{ip}"):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


def check_verify_otp_identity_limit(signup_id: str | None, email: str) -> None:
    """Call from verify_otp endpoint after parsing body. Raises 429 if over identity limit."""
    key = _identity_key(signup_id, email)
    if not verify_otp_per_identity.allow(f"verify_id:{key}"):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


def check_resend_otp_identity_limit(signup_id: str | None, email: str) -> None:
    """Call from resend_otp endpoint after parsing body. Raises 429 if over identity limit."""
    key = _identity_key(signup_id, email)
    if not resend_otp_per_identity.allow(f"resend_id:{key}"):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


def check_create_workspace_rate_limits(request: Request, platform_user_id: str) -> None:
    """Raises 429 if authenticated create-workspace limits exceeded."""
    from fastapi import HTTPException

    ip = _client_ip(request)
    if not create_workspace_per_ip.allow(f"create_ws_ip:{ip}"):
        raise HTTPException(status_code=429, detail="Too many workspace creations. Try again later.")
    if not create_workspace_per_user.allow(f"create_ws_user:{platform_user_id}"):
        raise HTTPException(
            status_code=429,
            detail="Too many workspace creations for this account. Try again later.",
        )


async def rate_limit_forgot_password(request: Request, email: str) -> None:
    """Check forgot-password rate limits (per IP + per email). Call after parsing body."""
    from fastapi import HTTPException
    ip = _client_ip(request)
    if not forgot_password_per_ip.allow(f"forgot_ip:{ip}"):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    key = _email_hash(email)
    if not forgot_password_per_email.allow(f"forgot_email:{key}"):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


async def rate_limit_login_ip(request: Request) -> None:
    """Per-IP login throttle (POST /auth/login). Safe to call before tenant is known (apex host)."""
    from fastapi import HTTPException

    ip = _client_ip(request)
    if not login_per_ip.allow(f"login_ip:{ip}"):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


async def rate_limit_login_tenant_email(request: Request, tenant_id: int, email_norm: str) -> None:
    """Per-workspace + email fingerprint throttle after tenant_id is known."""
    from fastapi import HTTPException

    eh = _email_hash(email_norm or "")
    if not login_per_tenant_email.allow(f"login_tid_mail:{int(tenant_id)}:{eh}"):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


async def rate_limit_login(request: Request, tenant_id: int, email_norm: str) -> None:
    """Check login rate limits (per IP + per tenant + email fingerprint)."""
    await rate_limit_login_ip(request)
    await rate_limit_login_tenant_email(request, tenant_id, email_norm)


async def rate_limit_workspace_intake_submit(request: Request, email_norm: str, phone: str) -> None:
    from fastapi import HTTPException

    ip = _client_ip(request)
    if not workspace_intake_submit_per_ip.allow(f"wi_submit_ip:{ip}"):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
    eh = _email_hash(email_norm)
    if not workspace_intake_submit_per_email.allow(f"wi_submit_email:{eh}"):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
    ph = _phone_fingerprint_hash(phone)
    if ph != "empty" and not workspace_intake_submit_per_phone.allow(f"wi_submit_phone:{ph}"):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")


async def rate_limit_workspace_intake_consume(request: Request) -> None:
    from fastapi import HTTPException

    ip = _client_ip(request)
    if not workspace_intake_consume_per_ip.allow(f"wi_consume_ip:{ip}"):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
