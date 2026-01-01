from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PlatformTenant(Base):
    __tablename__ = "platform_tenants"
    __table_args__ = (UniqueConstraint("slug", name="uq_platform_tenants_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PROVISIONING")
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
    db_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default="NOT_PROVISIONED")
    db_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    db_last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    members = relationship("PlatformTenantMember", back_populates="tenant", cascade="all, delete-orphan")


class PlatformUser(Base):
    __tablename__ = "platform_users"
    __table_args__ = (UniqueConstraint("email", name="uq_platform_users_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    verification_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    memberships = relationship("PlatformTenantMember", back_populates="platform_user", cascade="all, delete-orphan")


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
