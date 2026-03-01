"""Tenant-scoped token for invite links to person_applications (no platform DB)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ApplicationAccessToken(Base):
    __tablename__ = "application_access_tokens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["person_applications.tenant_id", "person_applications.id"],
            name="fk_application_access_tokens_tenant_app_to_applications",
            ondelete="CASCADE",
        ),
        Index("ix_application_access_tokens_tenant_application_id", "tenant_id", "application_id"),
        Index("ix_application_access_tokens_token", "token", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    application: Mapped["PersonApplication"] = relationship(
        "PersonApplication",
        back_populates="access_tokens",
    )
