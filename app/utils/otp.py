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

