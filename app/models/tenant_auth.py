"""Tenant-local authentication (tenant DB only). Not imported into platform Alembic metadata."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TenantUser(Base):
    __tablename__ = "tenant_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_norm", name="uq_tenant_users_tenant_email_norm"),
        ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_tenant_users_person",
            ondelete="SET NULL",
        ),
        Index("ix_tenant_users_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email_norm: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    theme: Mapped[str] = mapped_column(String(20), nullable=False, server_default="dark")
    person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    memberships: Mapped[list["TenantWorkspaceMember"]] = relationship(
        "TenantWorkspaceMember",
        back_populates="tenant_user",
        cascade="all, delete-orphan",
    )


class TenantWorkspaceMember(Base):
    """Runtime gate for app entry (with TenantUser credentials). Not person_roles."""

    __tablename__ = "tenant_workspace_members"
    __table_args__ = (
        UniqueConstraint("tenant_id", "tenant_user_id", name="uq_twm_tenant_user"),
        Index("ix_twm_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tenant_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="invited")
    role: Mapped[str] = mapped_column(String(50), nullable=False, server_default="TENANT_MEMBER")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant_user: Mapped["TenantUser"] = relationship("TenantUser", back_populates="memberships")


class TenantUserInvite(Base):
    __tablename__ = "tenant_user_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_tenant_user_invites_token_hash"),
        Index("ix_tenant_user_invites_tenant_user", "tenant_id", "tenant_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False
    )
    inviter_tenant_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
