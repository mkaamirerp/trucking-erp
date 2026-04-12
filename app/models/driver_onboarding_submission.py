# ACTIVE_ONBOARDING_2026Q1
# Legacy compatibility model only. PersonApplication is now the canonical onboarding
# intake/review path; keep this model until the legacy flow is fully retired.

from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, String, Text, func, desc
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DriverOnboardingSubmission(Base):
    __tablename__ = "driver_onboarding_submissions"
    __table_args__ = (
        Index("ix_driver_onboarding_submissions_tenant_status", "tenant_id", "status"),
        Index(
            "ix_driver_onboarding_submissions_tenant_created_at",
            "tenant_id",
            desc("created_at"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="driver_portal", server_default="driver_portal")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_street: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_postal: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    driver_license_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
