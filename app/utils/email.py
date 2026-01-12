"""
Simple SMTP email utilities for TruckERP.

Reads configuration from environment variables:
- SMTP_HOST
- SMTP_PORT
- SMTP_USERNAME
- SMTP_PASSWORD
- SMTP_FROM_ADDRESS
- SMTP_USE_TLS

Optional alert recipient:
- SIGNUP_ALERT_RECIPIENT (defaults to SMTP_FROM_ADDRESS)
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger(__name__)


def _get_bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


class SMTPConfig:
    def __init__(self) -> None:
        self.host: Optional[str] = os.getenv("SMTP_HOST")
        self.port: int = int(os.getenv("SMTP_PORT", "587"))
        self.username: Optional[str] = os.getenv("SMTP_USERNAME")
        self.password: Optional[str] = os.getenv("SMTP_PASSWORD")
        self.from_address: Optional[str] = os.getenv("SMTP_FROM_ADDRESS")
        self.use_tls: bool = _get_bool_env("SMTP_USE_TLS", True)

    def validate_basic(self) -> None:
        if not self.host:
            raise RuntimeError("SMTP_HOST is not set")
        if not self.from_address:
            raise RuntimeError("SMTP_FROM_ADDRESS is not set")


_config = SMTPConfig()


def _send_email_sync(to: str, subject: str, body: str, from_address: Optional[str] = None) -> None:
    _config.validate_basic()

    from_addr = from_address or _config.from_address
    if not from_addr:
        raise RuntimeError("From address is not configured")

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(_config.host, _config.port, timeout=10) as client:
            if _config.use_tls:
                client.starttls()
            if _config.username and _config.password:
                client.login(_config.username, _config.password)
            client.send_message(msg)
    except Exception as exc:
        logger.error(
            "SMTP send failed (host=%s, port=%s, use_tls=%s): %s",
            _config.host,
            _config.port,
            _config.use_tls,
            exc,
        )
        raise


async def send_email(to: str, subject: str, body: str, *, from_address: Optional[str] = None) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_email_sync, to, subject, body, from_address)


async def send_otp_email(to: str, otp: str) -> None:
    subject = "Your TruckERP verification code"
    body = (
        f"Your TruckERP verification code is: {otp}\n\n"
        "This code will expire in 10 minutes. If you did not request this code, you can ignore this email."
    )
    await send_email(to=to, subject=subject, body=body)


async def send_test_email(to: Optional[str] = None, subject: Optional[str] = None, body: Optional[str] = None) -> None:
    _config.validate_basic()

    recipient = to or _config.from_address
    if not recipient:
        raise RuntimeError("No recipient for test email and SMTP_FROM_ADDRESS is unset")

    subject = subject or "TruckERP SMTP connectivity test"
    body = body or "If you received this email, the TruckERP SMTP configuration is working."

    await send_email(to=recipient, subject=subject, body=body)


async def send_signup_failure_alert(
    *,
    first_name: Optional[str],
    last_name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    company_name: Optional[str],
    slug: Optional[str],
    error_message: str,
) -> None:
    """
    Best-effort alert when a signup fails unexpectedly so ops can follow up.
    """
    recipient = os.getenv("SIGNUP_ALERT_RECIPIENT") or _config.from_address
    if not recipient:
        raise RuntimeError("SIGNUP_ALERT_RECIPIENT or SMTP_FROM_ADDRESS must be configured for alerts")

    subject = f"Signup failed: {company_name or slug or email or 'unknown applicant'}"
    body_lines = [
        "A signup attempt failed.",
        "",
        f"Name: {(first_name or '').strip()} {(last_name or '').strip()}".strip(),
        f"Email: {email or 'N/A'}",
        f"Phone: {phone or 'N/A'}",
        f"Company: {company_name or 'N/A'}",
        f"Slug: {slug or 'N/A'}",
        "",
        f"Error: {error_message}",
    ]
    body = "\n".join(body_lines)

    try:
        await send_email(to=recipient, subject=subject, body=body)
    except Exception as exc:
        # Let caller decide how to react; avoid leaking credentials
        logger.warning("send_signup_failure_alert failed to deliver: %s", exc)


async def send_signup_welcome_email(
    *,
    to: str,
    company_name: str,
    slug: str,
    login_url: str,
    support_email: Optional[str] = None,
) -> None:
    """
    Sends a post-verification email with login instructions and workspace URL.
    """
    subject = "Your TruckERP workspace is ready"
    body_lines = [
        "Hi there,",
        "",
        f"Your workspace for {company_name} has been created.",
        "",
        "You can access it anytime at:",
        f"{login_url}",
        f"(Workspace slug: {slug})",
        "",
        "If this is your first time logging in, we’ll ask you to complete your company profile before you can use the dashboard.",
        "",
        "If you didn’t request this, you can ignore this email.",
    ]
    if support_email:
        body_lines.extend(["", f"Need help? Contact us at {support_email}."])

    body = "\n".join(body_lines)
    await send_email(to=to, subject=subject, body=body)
