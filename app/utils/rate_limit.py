"""
In-memory rate limiting for public OTP endpoints (verify-otp, resend-otp).

Limits are per IP and per identity (signup_id or email-hash) to prevent brute-force
and enumeration. Uses a simple sliding-window counter; safe for single-instance deployment.
For multi-instance, use Redis or similar in front.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict
from fastapi import Request


def _email_hash(email: str) -> str:
    """Stable hash for rate-limit key; avoids storing raw email."""
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()[:16]


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
