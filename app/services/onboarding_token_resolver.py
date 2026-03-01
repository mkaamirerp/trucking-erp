"""
Resolve onboarding invite token → (tenant_id, application_id) using platform DB only.
Used so applicant routes get tenant from token, not from host. All application data stays in tenant DB.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import OnboardingTokenLookup


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def resolve_onboarding_token(token: str, platform_db: AsyncSession) -> tuple[int, int]:
    """
    Look up token in platform DB. Returns (tenant_id, application_id) or raises HTTPException.
    - 401 if token missing/invalid
    - 410 if token expired
    """
    if not (token and token.strip()):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Onboarding token required")

    row = await platform_db.scalar(
        select(OnboardingTokenLookup)
        .where(OnboardingTokenLookup.token == token.strip())
        .limit(1)
    )
    if not row:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid onboarding link")

    if row.expires_at <= _utcnow():
        from fastapi import HTTPException

        raise HTTPException(status_code=410, detail="This onboarding link has expired")

    return (int(row.tenant_id), int(row.application_id))


async def set_applicant_context_from_token(
    request: Request,
    token: str,
    platform_db: AsyncSession,
) -> tuple[int, int]:
    """
    Resolve token via platform DB, set request.state.tenant_id and request.state.onboarding_application_id,
    return (tenant_id, application_id). Raises 401/410 on failure.
    """
    tenant_id, application_id = await resolve_onboarding_token(token, platform_db)
    request.state.tenant_id = tenant_id
    request.state.onboarding_application_id = application_id
    return (tenant_id, application_id)


