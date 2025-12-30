from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.platform import PlatformTenant, PlatformUser, PlatformTenantMember
from app.schemas.platform_signup import SignupRequest, SignupResponse, VerifyRequest, VerifyResponse

router = APIRouter(prefix="/api/v1/public", tags=["public-signup"])


def _slugify_company(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "tenant"


async def _ensure_unique_slug(base_slug: str, db: AsyncSession) -> str:
    attempt = base_slug
    suffix = 1
    while True:
        exists = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == attempt))
        if not exists:
            return attempt
        suffix += 1
        attempt = f"{base_slug}-{suffix}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def public_signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    # Unique email check
    existing = await db.scalar(select(PlatformUser).where(PlatformUser.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered.")

    base_slug = _slugify_company(payload.company_name)
    slug = await _ensure_unique_slug(base_slug, db)

    # Create verification token
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    user = PlatformUser(
        email=payload.email.lower(),
        first_name=payload.admin_first_name,
        last_name=payload.admin_last_name,
        phone=payload.phone,
        password_hash=None,
        is_email_verified=False,
        status="ACTIVE",
        verification_token_hash=token_hash,
        verification_token_expires_at=expires_at,
    )

    tenant = PlatformTenant(
        name=payload.company_name,
        slug=slug,
        status="PROVISIONING",
        plan=payload.plan_code or "trial",
        db_status="NOT_PROVISIONED",
        privacy_mode="standard",
        audit_visibility_mode="tenant_support",
    )

    db.add(user)
    await db.flush()
    tenant_owner = PlatformTenantMember(tenant=tenant, platform_user=user, role="TENANT_OWNER")
    db.add(tenant)
    db.add(tenant_owner)
    await db.commit()

    verification_token = token if settings.environment == "dev" else None
    message = "Signup successful. Please verify your email."

    # TODO: send real email using platform SMTP; for now, only return token in dev
    return SignupResponse(
        tenant_slug=slug,
        verification_required=True,
        verification_token=verification_token,
        message=message,
    )


@router.post("/verify-email", response_model=VerifyResponse)
async def verify_email(payload: VerifyRequest, db: AsyncSession = Depends(get_db)):
    token_hash = _hash_token(payload.token)
    now = datetime.now(timezone.utc)
    user = await db.scalar(
        select(PlatformUser).where(
            PlatformUser.verification_token_hash == token_hash,
            PlatformUser.verification_token_expires_at != None,  # noqa: E711
            PlatformUser.verification_token_expires_at > now,
        )
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")

    user.is_email_verified = True
    user.verification_token_hash = None
    user.verification_token_expires_at = None
    await db.commit()
    return VerifyResponse(message="Email verified.", verified=True)
