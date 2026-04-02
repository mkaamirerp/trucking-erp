"""Platform-only workspace intake helpers (tokens, expiry, continuation cookie)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.workspace_intake import (
    WORKSPACE_INTAKE_COOKIE_NAME,
    WORKSPACE_INTAKE_STATUS_CONSUMED,
    WORKSPACE_INTAKE_STATUS_EMAILED,
    WORKSPACE_INTAKE_STATUS_EXPIRED,
    WORKSPACE_INTAKE_STATUS_PENDING,
)
from app.models.platform import PlatformWorkspaceIntakeRequest


def hash_intake_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_ip_for_abuse(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(f"ip:{ip}".encode("utf-8")).hexdigest()[:32]


def hash_user_agent(ua: str | None) -> str | None:
    if not ua:
        return None
    return hashlib.sha256(ua.encode("utf-8")).hexdigest()[:32]


def normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def parse_continuation_cookie(raw: str | None) -> tuple[str, str] | None:
    if not raw or "." not in raw:
        return None
    left, _, right = raw.partition(".")
    if not left or not right:
        return None
    return left, right


async def maybe_expire_row(db: AsyncSession, row: PlatformWorkspaceIntakeRequest, now: datetime) -> None:
    if row.status == WORKSPACE_INTAKE_STATUS_CONSUMED:
        return
    if row.status == WORKSPACE_INTAKE_STATUS_EXPIRED:
        return
    if now <= row.expires_at:
        return
    if row.status in (WORKSPACE_INTAKE_STATUS_PENDING, WORKSPACE_INTAKE_STATUS_EMAILED):
        row.status = WORKSPACE_INTAKE_STATUS_EXPIRED
        row.updated_at = now
        await db.flush()


async def load_emailed_row_by_intake_token(
    db: AsyncSession, token_raw: str, now: datetime
) -> PlatformWorkspaceIntakeRequest | None:
    th = hash_intake_secret(token_raw)
    row = await db.scalar(select(PlatformWorkspaceIntakeRequest).where(PlatformWorkspaceIntakeRequest.intake_token_hash == th))
    if not row:
        return None
    await maybe_expire_row(db, row, now)
    return row


async def load_consumed_row_by_continuation(
    db: AsyncSession, request: Request, now: datetime
) -> PlatformWorkspaceIntakeRequest | None:
    raw_cookie = request.cookies.get(WORKSPACE_INTAKE_COOKIE_NAME)
    parsed = parse_continuation_cookie(raw_cookie)
    if not parsed:
        return None
    row_id, secret = parsed
    row = await db.scalar(select(PlatformWorkspaceIntakeRequest).where(PlatformWorkspaceIntakeRequest.id == row_id))
    if not row:
        return None
    await maybe_expire_row(db, row, now)
    if row.status != WORKSPACE_INTAKE_STATUS_CONSUMED:
        return None
    if not row.continuation_token_hash or not row.continuation_expires_at:
        return None
    if now > row.continuation_expires_at:
        return None
    if hash_intake_secret(secret) != row.continuation_token_hash:
        return None
    return row


async def intake_selected_package_for_signup(
    request: Request, db: AsyncSession, signup_email_norm: str, now: datetime
) -> str | None:
    """
    If a valid continuation cookie matches this signup email, return selected_package_code for onboarding payload.
    """
    row = await load_consumed_row_by_continuation(db, request, now)
    if not row:
        return None
    if (row.email or "").lower().strip() != signup_email_norm:
        return None
    return row.selected_package_code
