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
    OnboardingStatus,
    OTPPurpose,
    PlatformCompanyProfile,
    PlatformOnboardingPayload,
    PlatformOTPToken,
    PlatformSecurityEvent,
    PlatformSubscription,
    PlatformTenant,
    PlatformTenantMember,
    PlatformUser,
    SubscriptionPlan,
    SubscriptionStatus,
    TenantDBStatus,
    TenantMembership,
    TenantStatus,
)
from app.schemas.signup import (
    CompanySetupRequest,
    CompanySetupResponse,
    SignupRequest,
    SignupResponse,
    SlugAvailabilityResponse,
    SetupPrefillResponse,
    ResendOTPRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
    _normalize_phone_digits,
)
from app.utils.email import send_otp_email, send_signup_failure_alert, send_signup_welcome_email
from app.utils.jwt_auth import create_access_token, create_refresh_token, TokenType
from app.utils.otp import MAX_OTP_ATTEMPTS, check_otp, generate_otp, get_otp_expiration, hash_otp
from app.utils.rate_limit import (
    check_resend_otp_identity_limit,
    check_verify_otp_identity_limit,
    rate_limit_resend_otp,
    rate_limit_verify_otp,
)
from app.utils.slug import SLUG_REGEX, generate_slug_suggestions, is_slug_available, normalize_slug
from app.services.tenant_provisioning import provision_tenant_db
from app.utils.password import hash_password

router = APIRouter(prefix="/api/v1/public", tags=["public-signup"])
logger = logging.getLogger(__name__)

def _request_host(request: Request) -> str | None:
    host = request.headers.get("host") or request.url.hostname
    if not host:
        return None
    return host.split(":", 1)[0].lower().strip()


def _is_tenant_subdomain(host: str | None) -> bool:
    if not host:
        return False
    if host in {"localhost", "127.0.0.1"}:
        return False
    base_domain = (settings.base_domain or "").lower().strip()
    if not base_domain:
        return False
    if host == base_domain:
        return False
    if host in {f"www.{base_domain}", f"auth.{base_domain}"}:
        return False
    return host.endswith(f".{base_domain}")


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
async def public_signup(
    request: Request, response: Response, payload: SignupRequest, db: AsyncSession = Depends(get_db)
):
    """
    Step 1 of signup: validate slug + email, create server-side draft (PlatformOnboardingPayload),
    create OTP token, send OTP email, return { requires_otp: true, signup_id: <id> }.

    Anti-enumeration: email-already-exists and slug-taken are the only checks that can differ
    by real vs. fake email; we return a uniform "OTP sent" response in both edge cases rather
    than revealing which condition triggered.

    Does NOT create tenant, user, membership, subscription, or provision DB. No auth cookies.
    """
    async def notify_failure(error_message: str) -> None:
        try:
            await send_signup_failure_alert(
                first_name=payload.first_name or "",
                last_name=payload.last_name or "",
                email=payload.email,
                phone=payload.phone or None,
                company_name=payload.company_legal_name or payload.workspace_slug,
                slug=payload.workspace_slug,
                error_message=error_message,
            )
        except Exception as exc:
            logger.warning("signup_failure_alert_failed error=%s", exc)

    now = datetime.now(timezone.utc)

    try:
        if _is_tenant_subdomain(_request_host(request)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signup must be performed on truckerp.me, not a tenant subdomain.",
            )

        # ── record attempt (best-effort, non-blocking) ────────────────────────
        try:
            security_event = PlatformSecurityEvent(
                event_type="signup_attempt",
                email=payload.email,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                metadata_json={"slug": payload.workspace_slug},
            )
            db.add(security_event)
            await db.flush()
        except Exception as exc:
            logger.warning("signup_security_event_failed error=%s", exc)
            try:
                await db.rollback()
            except Exception:
                pass

        # ── validate slug format ──────────────────────────────────────────────
        normalized_slug = normalize_slug(payload.workspace_slug)
        if not SLUG_REGEX.match(normalized_slug):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slug must contain only lowercase letters, numbers, and hyphens",
            )

        # ── anti-enumeration: check email + slug together ─────────────────────
        # If email already exists we do NOT reveal it; just return the same
        # "OTP sent" shape.  Slug availability is a UX check (check-slug endpoint
        # is called first) so a 400 here is acceptable for slug collisions.
        email_lower = payload.email.lower()
        existing_user = await db.scalar(
            select(PlatformUser).where(PlatformUser.email == email_lower)
        )
        if existing_user:
            # Return the same shape as a normal signup so the caller cannot tell
            # whether the email is already registered.
            logger.info("signup_attempt_duplicate_email email=%s", email_lower)
            return SignupResponse(success=True, requires_otp=True)

        available = await is_slug_available(db, normalized_slug)
        if not available:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug is not available")

        # ── mark any previous PENDING drafts for this email as STALE ─────────
        stale_drafts = (
            await db.scalars(
                select(PlatformOnboardingPayload)
                .where(
                    PlatformOnboardingPayload.payload_json.op("->>")("email") == email_lower,
                    PlatformOnboardingPayload.status == OnboardingStatus.PENDING.value,
                    PlatformOnboardingPayload.tenant_id.is_(None),
                )
            )
        ).all()
        for old_draft in stale_drafts:
            old_draft.status = OnboardingStatus.STALE.value
            old_draft.updated_at = now

        # ── create new draft payload ──────────────────────────────────────────
        expires_at = now + timedelta(days=7)
        onboarding = PlatformOnboardingPayload(
            tenant_id=None,
            status=OnboardingStatus.PENDING.value,
            payload_json={
                "workspace_slug": normalized_slug,
                "email": email_lower,
                # Store only a hash (never plaintext) so password login can work post-OTP signup.
                "password_hash": hash_password(payload.password),
                "first_name": (payload.first_name or "").strip(),
                "last_name": (payload.last_name or "").strip(),
                "phone": payload.phone.strip() if payload.phone else None,
                "company_legal_name": payload.company_legal_name.strip(),
                "address": {
                    "street": payload.address.street.strip(),
                    "city": payload.address.city.strip(),
                    "region": payload.address.region.strip(),
                    "postal": payload.address.postal.strip(),
                    "country": payload.address.country.strip().upper(),
                },
            },
            expires_at=expires_at,
            consumed_at=None,
        )
        db.add(onboarding)
        await db.flush()  # get onboarding.id before creating OTP

        # ── create OTP token linked to the new draft ──────────────────────────
        otp = generate_otp()
        otp_row = PlatformOTPToken(
            purpose=OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
            email=email_lower,
            user_id=None,
            onboarding_payload_id=onboarding.id,
            otp_hash=hash_otp(otp),
            expires_at=get_otp_expiration(),
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(otp_row)
        await db.commit()

        # ── send OTP email (non-fatal) ────────────────────────────────────────
        try:
            await send_otp_email(email_lower, otp)
        except Exception as exc:
            logger.warning("send_otp_email_failed error=%s", exc)

        return SignupResponse(success=True, requires_otp=True, signup_id=onboarding.public_id)

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
async def verify_otp(
    payload: VerifyOTPRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_verify_otp),
):
    """
    Step 2 of signup: after OTP is valid, create tenant, user, memberships, subscription,
    provision tenant DB, set auth cookies, return redirect URL.

    Lookup order for OTP:
      1. If signup_id is provided → look up OTP by onboarding_payload_id (fast, exact)
      2. Fallback → latest non-consumed, non-superseded OTP for the email (legacy path)
    Transaction strategy (Option A):
      - All platform rows (tenant, user, memberships, subscription) + otp.consumed_at
        are written in a *single* commit AFTER provision_tenant_db succeeds.
      - If provision fails the platform DB rows are never committed.
    """
    context = {
        "email": payload.email.lower(),
        "signup_id": payload.signup_id,
        "slug": None,
        "tenant_id": None,
        "request_host": request.headers.get("host"),
        "db_name": None,
        "provisioning_step": "start",
    }
    try:
        now = datetime.now(timezone.utc)
        email_lower = payload.email.lower()

        # Per-identity rate limit (signup_id or email-hash)
        check_verify_otp_identity_limit(
            payload.signup_id if (payload.signup_id and payload.signup_id.strip()) else None,
            email_lower,
        )

        # ── 1. Locate OTP token ───────────────────────────────────────────────
        context["provisioning_step"] = "lookup_otp"
        otp_row = None
        signup_id_clean = (payload.signup_id or "").strip() or None

        if signup_id_clean:
            # Preferred: resolve payload by public_id (UUID), then OTP by onboarding_payload_id
            draft_by_public = await db.scalar(
                select(PlatformOnboardingPayload).where(
                    PlatformOnboardingPayload.public_id == signup_id_clean,
                )
            )
            if draft_by_public:
                otp_row = await db.scalar(
                    select(PlatformOTPToken)
                    .where(
                        PlatformOTPToken.onboarding_payload_id == draft_by_public.id,
                        PlatformOTPToken.purpose == OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
                        PlatformOTPToken.email == email_lower,
                    )
                    .order_by(PlatformOTPToken.created_at.desc())
                    .limit(1)
                )

        if otp_row is None:
            # Fallback: latest non-consumed, non-superseded OTP for email (uses ix_otp_tokens_email_created)
            otp_row = await db.scalar(
                select(PlatformOTPToken)
                .where(
                    PlatformOTPToken.email == email_lower,
                    PlatformOTPToken.purpose == OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
                    PlatformOTPToken.consumed_at.is_(None),
                    PlatformOTPToken.superseded_at.is_(None),
                )
                .order_by(PlatformOTPToken.created_at.desc())
                .limit(1)
            )

        if otp_row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code is no longer valid. Please request a new one.",
            )

        is_valid, reason = check_otp(payload.otp, otp_row)
        if not is_valid:
            if reason == "invalid":
                otp_row.failed_attempts = getattr(otp_row, "failed_attempts", 0) + 1
                await db.flush()
                if otp_row.failed_attempts >= MAX_OTP_ATTEMPTS:
                    otp_row.superseded_at = now
                    await db.flush()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Too many attempts. Request a new code.",
                    )
                left = MAX_OTP_ATTEMPTS - otp_row.failed_attempts
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Incorrect code. You have {left} attempt{'s' if left != 1 else ''} left.",
                )
            if reason == "too_many_attempts":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Too many attempts. Request a new code.",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code is no longer valid. Please request a new one.",
            )

        # ── 2. Locate the draft onboarding payload ────────────────────────────
        context["provisioning_step"] = "lookup_draft_payload"

        if otp_row.onboarding_payload_id is not None:
            # Fast path: OTP is linked to a specific payload
            draft_row = await db.get(PlatformOnboardingPayload, otp_row.onboarding_payload_id)
            if draft_row and draft_row.status not in (
                OnboardingStatus.PENDING.value, OnboardingStatus.FAILED.value
            ):
                draft_row = None  # Already consumed / stale
        else:
            # Legacy path: find latest PENDING draft matching email
            draft_row = await db.scalar(
                select(PlatformOnboardingPayload)
                .where(
                    PlatformOnboardingPayload.tenant_id.is_(None),
                    PlatformOnboardingPayload.consumed_at.is_(None),
                    PlatformOnboardingPayload.expires_at > now,
                    PlatformOnboardingPayload.payload_json.op("->>")("email") == email_lower,
                )
                .order_by(PlatformOnboardingPayload.created_at.desc())
                .limit(1)
            )

        if not draft_row or not draft_row.payload_json:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signup session expired or not found. Please sign up again.",
            )

        # Validate draft not already expired
        exp = draft_row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signup session expired. Please sign up again.",
            )

        # ── 3. Extract payload fields ─────────────────────────────────────────
        p = draft_row.payload_json
        normalized_slug = (p.get("workspace_slug") or "").strip().lower()
        if not normalized_slug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signup session")
        tenant_name = (p.get("company_legal_name") or normalized_slug).strip() or normalized_slug
        addr = p.get("address") or {}
        country_code = (addr.get("country") or "").strip().upper() or None
        first_name = (p.get("first_name") or "").strip()
        last_name = (p.get("last_name") or "").strip()
        email = (p.get("email") or email_lower).lower()
        phone_raw = p.get("phone")
        phone_digits = _normalize_phone_digits(phone_raw) if phone_raw else None

        # ── 4. Create all platform rows (NOT yet committed) ───────────────────
        context["provisioning_step"] = "create_tenant"
        tenant = PlatformTenant(
            name=tenant_name,
            slug=normalized_slug,
            status=TenantStatus.PENDING_SETUP.value,
            db_status=TenantDBStatus.NOT_CREATED.value,
            country_code=country_code,
        )
        db.add(tenant)
        await db.flush()

        draft_row.tenant_id = tenant.id
        draft_row.status = OnboardingStatus.COMPLETED.value
        draft_row.updated_at = now
        await db.flush()

        context["provisioning_step"] = "create_user"
        password_hash = p.get("password_hash") or None
        user = PlatformUser(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=password_hash,
            phone=f"+{phone_digits}" if phone_digits else None,
            is_email_verified=True,
            status="ACTIVE",
        )
        db.add(user)
        await db.flush()

        # Mark OTP consumed + link to newly created user
        otp_row.consumed_at = now
        otp_row.user_id = user.id

        context["provisioning_step"] = "create_membership"
        membership = PlatformTenantMember(tenant_id=tenant.id, platform_user_id=user.id, role="TENANT_ADMIN")
        db.add(membership)

        gate = TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            status="pending",
            is_break_glass_owner=True,
        )
        db.add(gate)

        subscription = PlatformSubscription(
            tenant_id=tenant.id,
            plan=SubscriptionPlan.TRIAL.value,
            status=SubscriptionStatus.TRIAL_ACTIVE.value,
            trial_ends_at=now + timedelta(days=14),
        )
        db.add(subscription)

        # ── 5. Provision tenant DB (before final commit) ──────────────────────
        # Flush so provision_tenant_db can see the tenant row in the same session.
        await db.flush()
        context["tenant_id"] = int(tenant.id)
        context["slug"] = tenant.slug
        context["provisioning_step"] = "provision_tenant_db"

        tenant = await provision_tenant_db(
            int(tenant.id),
            db,
            activate=True,
            creator_platform_user_id=user.id,
            creator_first_name=first_name,
            creator_last_name=last_name,
            creator_email=user.email,
        )
        context["db_name"] = tenant.db_name

        # Activate membership gate
        gate_row = await db.scalar(
            select(TenantMembership).where(
                TenantMembership.user_id == user.id,
                TenantMembership.tenant_id == tenant.id,
            )
        )
        if gate_row:
            gate_row.status = "active"

        # ── 6. Single final commit (Option A) ─────────────────────────────────
        await db.commit()

        # ── 7. Build redirect URLs ─────────────────────────────────────────────
        requires_company_setup = tenant.status == TenantStatus.PENDING_SETUP.value
        workspace_url = _workspace_url(
            request,
            tenant.slug,
            "/company-setup" if requires_company_setup else "/",
        )

        # ── 8. Welcome email (non-fatal) ──────────────────────────────────────
        try:
            await send_signup_welcome_email(
                to=user.email,
                company_name=tenant.name,
                slug=tenant.slug,
                login_url=workspace_url,
            )
        except Exception as exc:
            logger.warning("send_signup_welcome_email_failed error=%s", exc)

        # ── 9. Issue auth cookies ─────────────────────────────────────────────
        context["provisioning_step"] = "issue_tokens"
        access = create_access_token(
            user_id=user.id,
            tenant_id=int(tenant.id),
            tenant_slug=tenant.slug,
            roles=[membership.role],
        )
        refresh = create_refresh_token(
            user_id=user.id,
            tenant_id=int(tenant.id),
            tenant_slug=tenant.slug,
            roles=[membership.role],
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
            tenant_id=int(tenant.id),
            slug=tenant.slug,
        )
    except HTTPException:
        raise
    except IntegrityError:
        logger.exception("verify_otp failed", extra=context)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP verification conflict")
    except Exception as exc:
        logger.exception("verify_otp failed", extra=context)
        detail = "OTP verification failed"
        if settings.environment == "dev":
            detail = f"{detail}: {exc!s}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


@router.post("/resend-otp")
async def resend_otp(
    payload: ResendOTPRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_resend_otp),
):
    """
    Resend an OTP during the signup flow (pre-user state).

    Lookup order for the draft payload:
      1. If signup_id provided → look up PlatformOnboardingPayload by id
      2. Fallback → latest PENDING draft for the email

    Old non-consumed, non-superseded OTP tokens for the same payload are superseded.
    Always returns 200 (anti-enumeration: caller cannot tell if draft exists).
    """
    now = datetime.now(timezone.utc)
    email_lower = payload.email.lower()
    signup_id_clean = (payload.signup_id or "").strip() or None

    # Per-identity rate limit
    check_resend_otp_identity_limit(signup_id_clean, email_lower)

    try:
        # ── locate draft payload ──────────────────────────────────────────────
        draft_row = None

        if signup_id_clean:
            draft_row = await db.scalar(
                select(PlatformOnboardingPayload).where(
                    PlatformOnboardingPayload.public_id == signup_id_clean,
                )
            )
            if draft_row:
                stored_email = (draft_row.payload_json or {}).get("email", "").lower()
                if stored_email != email_lower:
                    draft_row = None
                elif draft_row.status not in (
                    OnboardingStatus.PENDING.value, OnboardingStatus.FAILED.value
                ):
                    draft_row = None

        if draft_row is None:
            draft_row = await db.scalar(
                select(PlatformOnboardingPayload)
                .where(
                    PlatformOnboardingPayload.payload_json.op("->>")("email") == email_lower,
                    PlatformOnboardingPayload.status == OnboardingStatus.PENDING.value,
                    PlatformOnboardingPayload.tenant_id.is_(None),
                    PlatformOnboardingPayload.expires_at > now,
                )
                .order_by(PlatformOnboardingPayload.created_at.desc())
                .limit(1)
            )

        if not draft_row:
            # Anti-enumeration: return success even when no draft found.
            logger.info("resend_otp_no_draft email=%s signup_id=%s", email_lower, payload.signup_id)
            return {"ok": True, "message": "If a pending signup exists for this email, a new code has been sent."}

        # ── 60s cooldown: reject resend if an OTP was sent for this payload in the last 60 seconds ───
        cooldown_cutoff = now - timedelta(seconds=60)
        recent = await db.scalar(
            select(PlatformOTPToken)
            .where(
                PlatformOTPToken.onboarding_payload_id == draft_row.id,
                PlatformOTPToken.created_at >= cooldown_cutoff,
            )
            .limit(1)
        )
        if recent is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait 60 seconds before requesting another code.",
            )

        # ── supersede all active (non-consumed, non-superseded) OTP tokens ────
        active_tokens = (
            await db.scalars(
                select(PlatformOTPToken).where(
                    PlatformOTPToken.onboarding_payload_id == draft_row.id,
                    PlatformOTPToken.consumed_at.is_(None),
                    PlatformOTPToken.superseded_at.is_(None),
                )
            )
        ).all()
        for old_token in active_tokens:
            old_token.superseded_at = now

        # ── issue new OTP linked to the same draft ────────────────────────────
        otp = generate_otp()
        new_otp_row = PlatformOTPToken(
            purpose=OTPPurpose.SIGNUP_EMAIL_VERIFY.value,
            email=email_lower,
            user_id=None,
            onboarding_payload_id=draft_row.id,
            otp_hash=hash_otp(otp),
            expires_at=get_otp_expiration(),
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(new_otp_row)
        await db.commit()

        try:
            await send_otp_email(email_lower, otp)
        except Exception as exc:
            logger.warning("resend_otp_send_failed error=%s", exc)

        debug_otp = otp if settings.environment == "dev" else None
        return {"ok": True, "message": "If a pending signup exists for this email, a new code has been sent.", "debug_otp": debug_otp}

    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception("resend_otp_failed email=%s", email_lower)
        # Always return 200 to prevent enumeration
        return {"ok": True, "message": "If a pending signup exists for this email, a new code has been sent."}


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


def _required_remaining_fields_for_country(country: str) -> list[str]:
    """Country-driven editable fields at step 3 (address + compliance)."""
    c = (country or "").upper()
    fields = ["address", "usdot_number"]
    if c == "US":
        fields.extend(["mc_number", "w9_upload"])
    elif c == "CA":
        fields.extend(["cvor_number", "hst_number"])
    return fields


@router.get("/company-setup/prefill", response_model=SetupPrefillResponse)
async def company_setup_prefill(request: Request, db: AsyncSession = Depends(get_db)):
    """Return prefill from onboarding payload (read-only) + required_remaining_fields. No profile yet."""
    tenant_id_header = request.headers.get("X-Tenant-ID")
    tenant_slug_header = request.headers.get("X-Tenant-Slug")
    if not tenant_id_header and not tenant_slug_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Tenant-ID or X-Tenant-Slug required")

    tenant = None
    if tenant_id_header:
        try:
            tenant = await db.get(PlatformTenant, int(tenant_id_header))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant id")
    elif tenant_slug_header:
        tenant = await db.scalar(
            select(PlatformTenant).where(PlatformTenant.slug == tenant_slug_header.strip().lower())
        )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    payload_row = await db.scalar(
        select(PlatformOnboardingPayload).where(
            PlatformOnboardingPayload.tenant_id == tenant.id,
            PlatformOnboardingPayload.consumed_at.is_(None),
            PlatformOnboardingPayload.expires_at > datetime.now(timezone.utc),
        )
    )
    if not payload_row or not payload_row.payload_json:
        country = (tenant.country_code or "US").upper()
        return SetupPrefillResponse(
            prefill={},
            required_remaining_fields=_required_remaining_fields_for_country(country),
            country=country,
        )

    p = payload_row.payload_json
    addr = p.get("address") or {}
    country = (addr.get("country") or tenant.country_code or "US").upper()
    prefill = {
        "company_legal_name": p.get("company_legal_name") or tenant.name,
        "country": country,
        "owner_email": p.get("email"),
        "address": addr,
    }
    return SetupPrefillResponse(
        prefill=prefill,
        required_remaining_fields=_required_remaining_fields_for_country(country),
        country=country,
    )


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

    # Final write: platform company profile (billing/display); consume onboarding payload if present
    onboarding = await db.scalar(
        select(PlatformOnboardingPayload).where(
            PlatformOnboardingPayload.tenant_id == tenant_id,
            PlatformOnboardingPayload.consumed_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    if onboarding:
        onboarding.consumed_at = now

    existing_profile = await db.scalar(
        select(PlatformCompanyProfile).where(PlatformCompanyProfile.tenant_id == tenant_id)
    )
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
