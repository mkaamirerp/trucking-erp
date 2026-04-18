from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TenantStatus(str, Enum):
    PENDING = "PENDING"
    PENDING_SETUP = "PENDING_SETUP"
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class TenantDBStatus(str, Enum):
    NOT_CREATED = "NOT_CREATED"
    NOT_PROVISIONED = "NOT_PROVISIONED"
    READY = "READY"
    ERROR = "ERROR"


class SubscriptionPlan(str, Enum):
    TRIAL = "TRIAL"
    PAID = "PAID"


class SubscriptionStatus(str, Enum):
    TRIAL_ACTIVE = "TRIAL_ACTIVE"
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class OTPPurpose(str, Enum):
    SIGNUP_EMAIL_VERIFY = "signup_email_verify"
    LOGIN_STEP_UP = "login_step_up"


class ReservedSlug(Base):
    __tablename__ = "reserved_slugs"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class PlatformTenant(Base):
    __tablename__ = "platform_tenants"
    __table_args__ = (UniqueConstraint("slug", name="uq_platform_tenants_slug"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=TenantStatus.PROVISIONING.value)
    plan: Mapped[str | None] = mapped_column(String(50), nullable=True)
    modules_json: Mapped[dict | None] = mapped_column("modules_enabled", JSONB, nullable=True)
    privacy_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="standard")
    audit_visibility_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="tenant_support")
    email_provider_type: Mapped[str] = mapped_column(String(50), nullable=False, default="platform_smtp")
    email_last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_last_test_result: Mapped[str | None] = mapped_column(String(255), nullable=True)

    db_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssl_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    provisioning_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    db_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default=TenantDBStatus.NOT_PROVISIONED.value)
    db_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    db_last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="America/Toronto")
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    billing_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_provider: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    # tenant: JWT sub = tenant_users.id; platform: legacy platform_users.id (UUID). Per-tenant cutover only.
    tenant_auth_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="platform", server_default="platform")
    #: When true (default), a global booking-broker match may auto-create a tenant `brokers` row. Opt out for suggest-only.
    broker_auto_create_from_global: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    #: People-level onboarding UI: combined (single surface) vs segmented (downstream HR/payroll/ops). Not driver-only.
    person_setup_ui_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="combined", default="combined"
    )
    #: How many days a document-request applicant link stays valid. Default 21.
    doc_request_link_expiry_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="21", default=21
    )

    members = relationship("PlatformTenantMember", back_populates="tenant", cascade="all, delete-orphan")
    subscriptions = relationship("PlatformSubscription", back_populates="tenant", cascade="all, delete-orphan")
    company_profile = relationship(
        "PlatformCompanyProfile", back_populates="tenant", cascade="all, delete-orphan", uselist=False
    )
    onboarding_payload = relationship(
        "PlatformOnboardingPayload", back_populates="tenant", cascade="all, delete-orphan", uselist=False
    )


class OnboardingStatus(str, Enum):
    PENDING = "PENDING"
    STALE = "STALE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PlatformOnboardingPayload(Base):
    """Server-side signup payload; prefill at setup, consumed on complete. Expires (e.g. 7 days)."""

    __tablename__ = "platform_onboarding_payloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=True, unique=True, index=True)
    normalized_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    normalized_slug: Mapped[str | None] = mapped_column(String(63), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OnboardingStatus.PENDING.value, server_default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("PlatformTenant", back_populates="onboarding_payload")
    otp_tokens: Mapped[list["PlatformOTPToken"]] = relationship("PlatformOTPToken", back_populates="onboarding_payload", cascade="all, delete-orphan")


class PlatformUser(Base):
    __tablename__ = "platform_users"
    __table_args__ = (UniqueConstraint("email", name="uq_platform_users_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    verification_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="dark", server_default="dark")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    memberships = relationship("PlatformTenantMember", back_populates="platform_user", cascade="all, delete-orphan")
    otp_tokens = relationship("PlatformOTPToken", back_populates="user", cascade="all, delete-orphan")


class PlatformTenantMember(Base):
    __tablename__ = "platform_tenant_members"
    __table_args__ = (UniqueConstraint("tenant_id", "platform_user_id", name="uq_platform_tenant_member_unique"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="TENANT_OWNER")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("PlatformTenant", back_populates="members")
    platform_user = relationship("PlatformUser", back_populates="memberships")


class TenantMembership(Base):
    """Platform membership gate: gates tenant access by status (active|suspended|pending|invited)."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_tenant_memberships_user_tenant"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    is_break_glass_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    tenant = relationship("PlatformTenant", backref="tenant_memberships")
    platform_user = relationship("PlatformUser", backref="tenant_memberships")


class PlatformSubscription(Base):
    __tablename__ = "platform_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default=SubscriptionPlan.TRIAL.value)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=SubscriptionStatus.TRIAL_ACTIVE.value)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("PlatformTenant", back_populates="subscriptions")


class PlatformLoginOtpChallenge(Base):
    """
    One server-side login step-up attempt: password verified for tenant+email, OTP pending, then single session issuance.
    """

    __tablename__ = "platform_login_otp_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email_norm: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    password_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformOTPToken(Base):
    __tablename__ = "platform_otp_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    login_challenge_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("platform_login_otp_challenges.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=True)
    onboarding_payload_id: Mapped[int | None] = mapped_column(
        ForeignKey("platform_onboarding_payloads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("PlatformUser", back_populates="otp_tokens")
    onboarding_payload: Mapped["PlatformOnboardingPayload | None"] = relationship(
        "PlatformOnboardingPayload", back_populates="otp_tokens", foreign_keys=[onboarding_payload_id]
    )


class PlatformSecurityEvent(Base):
    __tablename__ = "platform_security_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class PlatformCompanyProfile(Base):
    __tablename__ = "platform_company_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, unique=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_street: Mapped[str] = mapped_column(String(255), nullable=False)
    address_city: Mapped[str] = mapped_column(String(100), nullable=False)
    address_region: Mapped[str] = mapped_column(String(100), nullable=False)
    address_postal: Mapped[str] = mapped_column(String(20), nullable=False)
    address_country: Mapped[str] = mapped_column(String(2), nullable=False)
    company_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usdot_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mc_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cvor_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    operator_license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hst_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    w9_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    w9_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("PlatformTenant", back_populates="company_profile")


class OnboardingTokenLookup(Base):
    """
    Platform-only: resolve onboarding invite token -> (tenant_id, application_id).
    Used so applicant routes can resolve tenant from token, not from host.
    All application data stays in tenant DB.
    """
    __tablename__ = "onboarding_token_lookup"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlatformLoginUnlockStepUpPending(Base):
    """
    Platform-only: after an operator clears sign-in friction for a workspace+identity, the next successful
    password verification must complete login step-up (OTP) once. Row deleted when step-up completes session issuance.
    Does not replace password-fail streak rules; complements unlock that clears streak state.
    """

    __tablename__ = "platform_login_unlock_step_up_pending"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_fingerprint", name="uq_plusup_tenant_fp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlatformLoginPasswordFailStreak(Base):
    """
    Platform-only: sliding-window count of consecutive failed password verifications per tenant + email fingerprint.
    Used to require human verification (Turnstile) before the next password check when armed.
    """

    __tablename__ = "platform_login_password_fail_streaks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_fingerprint", name="uq_plpfs_tenant_fp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)
    streak_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlatformLoginFailureEvent(Base):
    """Platform-only audit of tenant login failures (operator diagnostics; not for tenant DB)."""

    __tablename__ = "platform_login_failure_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_slug: Mapped[str] = mapped_column(String(63), nullable=False)
    tenant_auth_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_host: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PlatformTenantUserMap(Base):
    """Maps platform_users.id to tenant_users.id per workspace for dual-write and rollback."""

    __tablename__ = "platform_tenant_user_map"
    __table_args__ = (
        UniqueConstraint("platform_user_id", "tenant_id", name="uq_ptum_platform_tenant"),
        UniqueConstraint("tenant_id", "tenant_user_id", name="uq_ptum_tenant_tuser"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class UserInvite(Base):
    """Tenant-admin invite: token for new/invited users to set password and activate membership."""
    __tablename__ = "user_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    inviter_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platform_users.id", ondelete="SET NULL"), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class PlatformWorkspaceIntakeRequest(Base):
    """Minimal public intake before full signup; platform DB only (no tenant access)."""

    __tablename__ = "platform_workspace_intake_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_package_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    intake_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    continuation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    continuation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlatformGmailMailboxIndex(Base):
    """Maps normalized Gmail address to platform tenant for Pub/Sub ingestion webhooks (no tenant Host header)."""

    __tablename__ = "platform_gmail_mailbox_index"
    __table_args__ = (UniqueConstraint("gmail_address_norm", name="uq_platform_gmail_mailbox_index_norm"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    gmail_address_norm: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
