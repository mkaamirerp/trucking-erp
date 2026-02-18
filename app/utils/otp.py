from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone


def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP of the given length."""
    bound = 10 ** length
    return f"{secrets.randbelow(bound):0{length}d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def get_otp_expiration(minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def check_otp(candidate: str, otp_token) -> tuple[bool, str | None]:
    """Validate an OTP candidate against a PlatformOTPToken row.

    Returns (is_valid, error_reason).
    error_reason is None when valid, or a short string describing the failure.

    Checks (in order):
      1. Already consumed  → "already_used"
      2. Superseded        → "superseded"
      3. Expired           → "expired"
      4. Hash mismatch     → "invalid"
    """
    now = datetime.now(timezone.utc)

    if otp_token.consumed_at is not None:
        return False, "already_used"

    if otp_token.superseded_at is not None:
        return False, "superseded"

    exp = otp_token.expires_at
    # Make tz-aware if the DB returned a naive datetime
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        return False, "expired"

    if hash_otp(candidate) != otp_token.otp_hash:
        return False, "invalid"

    return True, None

