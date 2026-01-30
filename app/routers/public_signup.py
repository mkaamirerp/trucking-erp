from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status, File, UploadFile, Response
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.storage import save_company_doc_upload_local
from app.models.platform import (
    OTPPurpose,
    PlatformCompanyProfile,
    PlatformOTPToken,
    PlatformSecurityEvent,
    PlatformSubscription,
    PlatformTenant,
    PlatformTenantMember,
    PlatformUser,
    SubscriptionPlan,
    SubscriptionStatus,
    TenantDBStatus,
    TenantStatus,
)
from app.schemas.signup import (
    CompanySetupRequest,
    CompanySetupResponse,
    SignupRequest,
    SignupResponse,
    SlugAvailabilityResponse,
    ResendOTPRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.utils.email import send_otp_email, send_signup_failure_alert, send_signup_welcome_email
from app.utils.jwt_auth import create_access_token, create_refresh_token, TokenType
from app.utils.otp import generate_otp, get_otp_expiration, hash_otp
from app.utils.password import hash_password
from app.utils.slug import SLUG_REGEX, generate_slug_suggestions, is_slug_available, normalize_slug
from app.services.tenant_provisioning import provision_tenant_db

router = APIRouter(prefix="/api/v1/public", tags=["public-signup"])
logger = logging.getLogger(__name__)


@router.get("/tenant/{slug}")
async def get_tenant_status(slug: str, db: AsyncSession = Depends(get_db)):
    """
    Public endpoint to check tenant status by slug.
    
    Returns tenant status information without requiring authentication.
    Used by frontend to validate tenant before routing to protected pages.
    
    Returns:
    - 200: Tenant exists and is ACTIVE/READY
    - 404: Tenant does not exist
    - 403: Tenant exists but is NOT ACTIVE or NOT READY
    """
    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == slug.lower().strip()))
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )
    
    if tenant.status == TenantStatus.SUSPENDED.value:
        return {
            "exists": True,
            "slug": tenant.slug,
            "status": tenant.status,
            "db_status": tenant.db_status,
            "ready": False,
            "reason": "Tenant account is suspended",
        }

    if tenant.db_status != TenantDBStatus.READY.value:
        return {
            "exists": True,
            "slug": tenant.slug,
            "status": tenant.status,
            "db_status": tenant.db_status,
            "ready": False,
            "reason": "Tenant database is not ready",
        }

    # Tenant is ready for app access only when ACTIVE
    return {
        "exists": True,
        "slug": tenant.slug,
        "status": tenant.status,
        "db_status": tenant.db_status,
        "ready": tenant.status == TenantStatus.ACTIVE.value,
    }


@router.get("/check-slug-availability", response_model=SlugAvailabilityResponse)
async def check_slug_availability(slug: str, db: AsyncSession = Depends(get_db)):
    normalized = normalize_slug(slug)
    # Reject if normalization altered invalid characters or pattern does not match
    if normalized != slug.strip().lower() or not SLUG_REGEX.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slug must contain only lowercase letters, numbers, and hyphens",
        )
    available = await is_slug_available(db, normalized)
    if available:
        return SlugAvailabilityResponse(available=True, slug=normalized, suggestions=None)
    suggestions = await generate_slug_suggestions(db, normalized)
    return SlugAvailabilityResponse(available=False, slug=normalized, suggestions=suggestions)


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def public_signup(request: Request, payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    async def notify_failure(error_message: str) -> None:
        try:
            await send_signup_failure_alert(
                first_name=payload.first_name,
                last_name=payload.last_name,
                email=payload.email,
                phone=payload.phone,
                company_name=payload.company_name,
                slug=payload.slug,
                error_message=error_message,
            )
        except Exception as exc:
            logger.warning("signup_failure_alert_failed error=%s", exc)

    try:
        # Security event log
        try:
            security_event = PlatformSecurityEvent(
                event_type="signup_attempt",
                email=payload.email,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                metadata_json={"slug": payload.slug, "country": payload.country, "phone": payload.phone},
            )
            db.add(security_event)
            await db.flush()
        except Exception as exc:
            logger.warning("signup_security_event_failed error=%s", exc)
            try:
                await db.rollback()
            except Exception:
                pass

        # Email uniqueness (allow resend OTP if unverified)
        existing = await db.scalar(select(PlatformUser).where(PlatformUser.email == payload.email.lower()))
        if existing:
            if existing.is_email_verified:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists"
                )
            membership = await db.scalar(
                select(PlatformTenantMember).where(PlatformTenantMember.platform_user_id == existing.id)
            )
            tenant = None
            if membership:
                tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == membership.tenant_id))
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Account exists but workspace is missing. Contact support.",
                )

            normalized_slug = normalize_slug(payload.slug)
            if normalized_slug != tenant.slug:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered for another workspace",
                )

            otp = generate_otp()
            otp_hash = hash_otp(otp)
            otp_row = PlatformOTPToken(
                purpose=OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
                email=existing.email,
                user_id=existing.id,
                otp_hash=otp_hash,
                expires_at=get_otp_expiration(),
                request_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            db.add(otp_row)
            try:
                await send_otp_email(existing.email, otp)
            except Exception as exc:
                logger.warning("signup_otp_resend_failed error=%s", exc)
            await db.commit()

            debug_otp = otp if settings.environment == "dev" else None
            return SignupResponse(
                success=True,
                message="OTP resent. Please check your email for the verification code.",
                user_id=existing.id,
                tenant_id=tenant.id,
                email=existing.email,
                debug_otp=debug_otp,
            )

        normalized_slug = normalize_slug(payload.slug)
        if not SLUG_REGEX.match(normalized_slug):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slug must contain only lowercase letters, numbers, and hyphens",
            )

        available = await is_slug_available(db, normalized_slug)
        if not available:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug is not available")

        tenant = PlatformTenant(
            name=payload.company_name.strip(),
            slug=normalized_slug,
            status=TenantStatus.PENDING_SETUP.value,
            db_status=TenantDBStatus.NOT_CREATED.value,
            country_code=payload.country,
        )
        db.add(tenant)
        await db.flush()

        user = PlatformUser(
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=payload.email.lower(),
            phone=payload.phone.strip() if payload.phone else None,
            password_hash=hash_password(payload.password),
            is_email_verified=False,
            status="ACTIVE",
        )
        db.add(user)
        await db.flush()

        membership = PlatformTenantMember(tenant_id=tenant.id, platform_user_id=user.id, role="TENANT_ADMIN")
        db.add(membership)

        subscription = PlatformSubscription(
            tenant_id=tenant.id,
            plan=SubscriptionPlan.TRIAL.value,
            status=SubscriptionStatus.TRIAL_ACTIVE.value,
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.add(subscription)

        otp = generate_otp()
        otp_hash = hash_otp(otp)
        otp_row = PlatformOTPToken(
            purpose=OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
            email=user.email,
            user_id=user.id,
            otp_hash=otp_hash,
            expires_at=get_otp_expiration(),
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(otp_row)

        # Try to send OTP email (best-effort)
        try:
            await send_otp_email(user.email, otp)
        except Exception as exc:
            try:
                smtp_event = PlatformSecurityEvent(
                    event_type="smtp_delivery_failed",
                    email=user.email,
                    user_id=user.id,
                    tenant_id=tenant.id,
                    ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    metadata_json={
                        "reason": "OTP email send failed",
                        "error": str(exc),
                        "slug": tenant.slug,
                    },
                )
                db.add(smtp_event)
                await db.flush()
            except Exception as exc2:
                logger.warning("smtp_event_log_failed error=%s", exc2)
                try:
                    await db.rollback()
                except Exception:
                    pass
            # Also alert ops so they can follow up with the user
            await notify_failure(f"OTP email send failed: {exc}")

        await db.commit()

        debug_otp = otp if settings.environment == "dev" else None
        return SignupResponse(
            success=True,
            message="Signup successful. Please check your email for the verification code.",
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            debug_otp=debug_otp,
        )
    except HTTPException:
        try:
            await db.rollback()
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        await notify_failure(str(exc))
        logger.exception("public_signup_failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


def _workspace_url(request: Request, slug: str, path_suffix: str = "/company-setup") -> str:
    """
    Builds a workspace URL using subdomain pattern: https://{slug}.{base_domain}{path_suffix}
    Falls back to request host if base_domain is missing.
    """
    base_domain = settings.base_domain or request.url.hostname or "localhost"
    scheme = request.url.scheme or "https"
    suffix = path_suffix if path_suffix.startswith("/") else f"/{path_suffix}"
    return f"{scheme}://{slug}.{base_domain}{suffix}"


def _account_setup_missing_for_payload(country: str, payload: CompanySetupRequest) -> list[str]:
    missing: list[str] = []
    country = (country or "").upper()

    def _require(label: str, value: str | None) -> None:
        if not value or not str(value).strip():
            missing.append(label)

    # Address
    if not all(
        [
            payload.address.street,
            payload.address.city,
            payload.address.region,
            payload.address.postal,
            payload.address.country,
        ]
    ):
        missing.append("company_address")

    if country == "US":
        _require("mc_number", payload.mc_number)
        _require("usdot_number", payload.usdot_number)
        _require("w9_upload", payload.w9_storage_key)
    elif country == "CA":
        _require("cvor_number", payload.cvor_number)
        _require("hst_number", payload.hst_number)

    return missing


@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp(payload: VerifyOTPRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    context = {
        "email": payload.email.lower(),
        "slug": None,
        "tenant_id": None,
        "request_host": request.headers.get("host"),
        "db_name": None,
        "provisioning_step": "start",
    }
    step = "start"
    try:
        now = datetime.now(timezone.utc)
        step = "lookup_otp"
        context["provisioning_step"] = step
        otp_row = await db.scalar(
            select(PlatformOTPToken)
            .where(
                PlatformOTPToken.email == payload.email.lower(),
                PlatformOTPToken.purpose == OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
                PlatformOTPToken.consumed_at.is_(None),
                PlatformOTPToken.expires_at > now,
            )
            .order_by(PlatformOTPToken.created_at.desc())
        )
        if not otp_row or otp_row.otp_hash != hash_otp(payload.otp):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")

        otp_row.consumed_at = now

        step = "lookup_user"
        context["provisioning_step"] = step
        user = await db.scalar(select(PlatformUser).where(PlatformUser.id == otp_row.user_id))
        if user:
            user.is_email_verified = True

        step = "lookup_membership"
        context["provisioning_step"] = step
        membership = await db.scalar(
            select(PlatformTenantMember).where(PlatformTenantMember.platform_user_id == otp_row.user_id)
        )
        tenant = None
        if membership:
            step = "lookup_tenant"
            context["provisioning_step"] = step
            tenant = await db.scalar(
                select(PlatformTenant)
                .options(selectinload(PlatformTenant.company_profile))
                .where(PlatformTenant.id == membership.tenant_id)
            )

        await db.commit()

        requires_company_setup = True
        workspace_url = ""
        tenant_id: int | None = None
        tenant_slug: str | None = None
        if tenant:
            context["tenant_id"] = int(tenant.id)
            context["slug"] = tenant.slug
            context["db_name"] = tenant.db_name

            if tenant.status == TenantStatus.SUSPENDED.value:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant suspended")

            requires_company_setup = tenant.status == TenantStatus.PENDING_SETUP.value
            tenant_id = int(tenant.id)
            tenant_slug = tenant.slug
            if requires_company_setup and tenant.db_status != TenantDBStatus.READY.value:
                step = "provision_tenant_db"
                context["provisioning_step"] = step
                tenant = await provision_tenant_db(int(tenant.id), db, activate=False)
                context["db_name"] = tenant.db_name

            if requires_company_setup and tenant.db_status != TenantDBStatus.READY.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Tenant provisioning in progress",
                )

            workspace_url = _workspace_url(
                request,
                tenant.slug,
                "/company-setup" if requires_company_setup else "/dashboard",
            )

        # Send post-verification welcome email (best-effort)
        try:
            if tenant and user:
                login_url = workspace_url or _workspace_url(request, tenant.slug, "/company-setup")
                await send_signup_welcome_email(
                    to=user.email,
                    company_name=tenant.name,
                    slug=tenant.slug,
                    login_url=login_url,
                )
        except Exception as exc:
            logger.warning("send_signup_welcome_email_failed error=%s", exc)

        # Issue tokens
        if tenant and user:
            step = "issue_tokens"
            context["provisioning_step"] = step
            access = create_access_token(
                user_id=user.id,
                tenant_id=int(tenant.id),
                tenant_slug=tenant.slug,
                roles=[membership.role] if membership else [],
            )
            refresh = create_refresh_token(
                user_id=user.id,
                tenant_id=int(tenant.id),
                tenant_slug=tenant.slug,
                roles=[membership.role] if membership else [],
            )
            secure = bool(settings.secure_cookies)
            domain = settings.cookie_domain or (f".{settings.base_domain}" if settings.base_domain else None)
            response.set_cookie(
                "access_token",
                access,
                httponly=True,
                secure=secure,
                samesite=settings.jwt_same_site,
                domain=domain,
                max_age=settings.jwt_access_minutes * 60,
                path="/",
            )
            response.set_cookie(
                "refresh_token",
                refresh,
                httponly=True,
                secure=secure,
                samesite=settings.jwt_same_site,
                domain=domain,
                max_age=settings.jwt_refresh_days * 24 * 3600,
                path="/api/v1/auth/refresh",
            )

        return VerifyOTPResponse(
            message="Email verified.",
            verified=True,
            requires_company_setup=requires_company_setup,
            workspace_url=workspace_url,
            tenant_id=tenant_id,
            slug=tenant_slug,
        )
    except HTTPException:
        raise
    except IntegrityError:
        logger.exception("verify_otp failed", extra=context)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP verification conflict")
    except Exception:
        logger.exception("verify_otp failed", extra=context)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OTP verification failed")


@router.post("/resend-otp")
async def resend_otp(payload: ResendOTPRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(PlatformUser).where(PlatformUser.email == payload.email.lower()))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    otp = generate_otp()
    otp_hash = hash_otp(otp)
    otp_row = PlatformOTPToken(
        purpose=OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
        email=user.email,
        user_id=user.id,
        otp_hash=otp_hash,
        expires_at=get_otp_expiration(),
        request_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(otp_row)
    await db.commit()

    try:
        await send_otp_email(user.email, otp)
    except Exception as exc:
        logger.warning("resend_otp_failed error=%s", exc)

    debug_otp = otp if settings.environment == "dev" else None
    return {"ok": True, "message": "OTP resent.", "debug_otp": debug_otp}


@router.post("/company-setup/w9-upload")
async def upload_w9_document(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    tenant_id_header = request.headers.get("X-Tenant-ID")
    tenant_slug_header = request.headers.get("X-Tenant-Slug")

    if not tenant_id_header and not tenant_slug_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Tenant-ID or X-Tenant-Slug required")

    tenant = None
    if tenant_id_header:
        try:
            tenant_id = int(tenant_id_header)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant id")
        tenant = await db.get(PlatformTenant, tenant_id)
    elif tenant_slug_header:
        tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug_header.strip().lower()))

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    stored = await save_company_doc_upload_local(file)
    return {
        "storage_key": stored.storage_key,
        "original_filename": stored.original_filename,
        "content_type": stored.content_type,
        "file_size_bytes": stored.file_size_bytes,
        "sha256": stored.sha256,
    }


@router.post("/company-setup", response_model=CompanySetupResponse)
async def company_setup(payload: CompanySetupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Determine tenant from membership; this assumes authenticated user context is supplied via headers
    tenant_id_header = request.headers.get("X-Tenant-ID")
    tenant_slug_header = request.headers.get("X-Tenant-Slug")

    if not tenant_id_header and not tenant_slug_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Tenant-ID or X-Tenant-Slug required")

    tenant = None
    tenant_id = None

    if tenant_id_header:
        try:
            tenant_id = int(tenant_id_header)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant id")
        tenant = await db.get(PlatformTenant, tenant_id)
    elif tenant_slug_header:
        tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug_header.strip().lower()))
        tenant_id = tenant.id if tenant else None

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    country = (tenant.country_code or payload.address.country or "").upper()
    missing = _account_setup_missing_for_payload(country, payload)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    tenant.country_code = country

    # Upsert company profile
    existing_profile = await db.scalar(
        select(PlatformCompanyProfile).where(PlatformCompanyProfile.tenant_id == tenant_id)
    )
    now = datetime.now(timezone.utc)
    if existing_profile:
        profile = existing_profile
        profile.legal_name = payload.legal_name
        profile.address_street = payload.address.street
        profile.address_city = payload.address.city
        profile.address_region = payload.address.region
        profile.address_postal = payload.address.postal
        profile.address_country = payload.address.country
        profile.usdot_number = payload.usdot_number
        profile.mc_number = payload.mc_number
        profile.cvor_number = payload.cvor_number
        profile.operator_license = payload.operator_license
        profile.hst_number = payload.hst_number
        profile.w9_storage_key = payload.w9_storage_key
        profile.w9_original_filename = payload.w9_original_filename
        profile.setup_completed_at = now
    else:
        profile = PlatformCompanyProfile(
            tenant_id=tenant_id,
            legal_name=payload.legal_name,
            address_street=payload.address.street,
            address_city=payload.address.city,
            address_region=payload.address.region,
            address_postal=payload.address.postal,
            address_country=payload.address.country,
            usdot_number=payload.usdot_number,
            mc_number=payload.mc_number,
            cvor_number=payload.cvor_number,
            operator_license=payload.operator_license,
            hst_number=payload.hst_number,
            w9_storage_key=payload.w9_storage_key,
            w9_original_filename=payload.w9_original_filename,
            setup_completed_at=now,
        )
        db.add(profile)

    await db.commit()

    tenant = await provision_tenant_db(int(tenant.id), db)
    dashboard_url = _workspace_url(request, tenant.slug, "/dashboard")
    return CompanySetupResponse(tenant_status=tenant.status, db_status=tenant.db_status, dashboard_url=dashboard_url)
