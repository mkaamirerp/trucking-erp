"""Public workspace intake: platform DB only; gates /create-workspace via email link + continuation cookie."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.workspace_intake import (
    WORKSPACE_INTAKE_CONTINUATION_TTL_SEC,
    WORKSPACE_INTAKE_COOKIE_NAME,
    WORKSPACE_INTAKE_LINK_TTL_SEC,
    WORKSPACE_INTAKE_STATUS_CONSUMED,
    WORKSPACE_INTAKE_STATUS_EMAILED,
    WORKSPACE_INTAKE_STATUS_EXPIRED,
    WORKSPACE_INTAKE_STATUS_PENDING,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.platform import PlatformWorkspaceIntakeRequest
from app.schemas.workspace_intake import (
    WorkspaceIntakeConsumeRequest,
    WorkspaceIntakeConsumeResponse,
    WorkspaceIntakeCreateRequest,
    WorkspaceIntakeCreateResponse,
    WorkspaceIntakeSessionResponse,
)
from app.services.workspace_intake import (
    hash_intake_secret,
    hash_ip_for_abuse,
    hash_user_agent,
    load_consumed_row_by_continuation,
    load_emailed_row_by_intake_token,
)
from app.utils.email import send_workspace_intake_continue_email
from app.utils.rate_limit import rate_limit_workspace_intake_consume, rate_limit_workspace_intake_submit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace-intake"])


def _web_app_base_url() -> str:
    env = os.getenv("PUBLIC_WEB_BASE_URL")
    if env:
        return env.rstrip("/")
    if settings.base_domain:
        return f"https://{settings.base_domain}".rstrip("/")
    return "https://truckerp.me"


def _intake_continue_url(intake_token: str) -> str:
    return f"{_web_app_base_url()}/create-workspace?intake_token={intake_token}"


def _continuation_cookie_params() -> dict:
    secure = bool(settings.secure_cookies)
    domain = settings.cookie_domain or (f".{settings.base_domain}" if settings.base_domain else None)
    return {
        "httponly": True,
        "secure": secure,
        "samesite": settings.jwt_same_site,
        "domain": domain,
        "path": "/",
        "max_age": WORKSPACE_INTAKE_CONTINUATION_TTL_SEC,
    }


@router.post("/workspace-intake", response_model=WorkspaceIntakeCreateResponse)
async def create_workspace_intake(
    request: Request,
    body: WorkspaceIntakeCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    await rate_limit_workspace_intake_submit(request, str(body.email).lower(), body.phone_number)
    now = datetime.now(timezone.utc)
    email_norm = str(body.email).lower().strip()
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_intake_secret(raw_token)
    expires_at = now + timedelta(seconds=WORKSPACE_INTAKE_LINK_TTL_SEC)

    row = PlatformWorkspaceIntakeRequest(
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        email=email_norm,
        phone_number=body.phone_number.strip(),
        selected_package_code=body.selected_package_code,
        status=WORKSPACE_INTAKE_STATUS_PENDING,
        intake_token_hash=token_hash,
        expires_at=expires_at,
        consumed_at=None,
        continuation_token_hash=None,
        continuation_expires_at=None,
        client_ip_hash=hash_ip_for_abuse(request.client.host if request.client else None),
        user_agent_hash=hash_user_agent(request.headers.get("user-agent")),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    url = _intake_continue_url(raw_token)
    try:
        await send_workspace_intake_continue_email(to=email_norm, continue_url=url)
    except Exception:
        logger.exception("workspace_intake_email_failed email=%s row_id=%s", email_norm, row.id)
        await db.rollback()
        return WorkspaceIntakeCreateResponse()

    row.status = WORKSPACE_INTAKE_STATUS_EMAILED
    row.updated_at = now
    await db.commit()
    return WorkspaceIntakeCreateResponse()


@router.post("/workspace-intake/consume", response_model=WorkspaceIntakeConsumeResponse)
async def consume_workspace_intake(
    request: Request,
    response: Response,
    body: WorkspaceIntakeConsumeRequest,
    db: AsyncSession = Depends(get_db),
):
    await rate_limit_workspace_intake_consume(request)
    now = datetime.now(timezone.utc)
    row = await load_emailed_row_by_intake_token(db, body.intake_token.strip(), now)
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link.")
    if row.status == WORKSPACE_INTAKE_STATUS_EXPIRED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link.")
    if row.status == WORKSPACE_INTAKE_STATUS_CONSUMED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This link has already been used.")
    if row.status == WORKSPACE_INTAKE_STATUS_PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link.")
    if row.status != WORKSPACE_INTAKE_STATUS_EMAILED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link.")

    cont_raw = secrets.token_urlsafe(32)
    row.status = WORKSPACE_INTAKE_STATUS_CONSUMED
    row.consumed_at = now
    row.continuation_token_hash = hash_intake_secret(cont_raw)
    row.continuation_expires_at = now + timedelta(seconds=WORKSPACE_INTAKE_CONTINUATION_TTL_SEC)
    row.updated_at = now
    await db.commit()

    cookie_value = f"{row.id}.{cont_raw}"
    response.set_cookie(WORKSPACE_INTAKE_COOKIE_NAME, cookie_value, **_continuation_cookie_params())

    return WorkspaceIntakeConsumeResponse(
        selected_package_code=row.selected_package_code,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        phone_number=row.phone_number,
    )


@router.get("/workspace-intake/session", response_model=WorkspaceIntakeSessionResponse)
async def workspace_intake_session(request: Request, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    row = await load_consumed_row_by_continuation(db, request, now)
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active workspace intake session.")
    return WorkspaceIntakeSessionResponse(
        selected_package_code=row.selected_package_code,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        phone_number=row.phone_number,
    )
