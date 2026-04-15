"""Canonical tenant-scoped onboarding intake/review record for invite-link applications.

application_type = onboarding workflow / form track. Controls which form the applicant sees.
requested_role_code = role assigned on approval (person_roles.role_code). Kept separate.
For MVP invite creation both are set to the same value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

APPLICATION_TYPES = frozenset(
    {"DRIVER", "DISPATCHER", "HR", "MECHANIC", "PAYROLL", "SAFETY", "OFFICE_ADMIN", "OTHER"}
)


class PersonApplication(Base):
    __tablename__ = "person_applications"
    __table_args__ = (
        Index("ix_person_applications_tenant_id", "tenant_id"),
        Index("ix_person_applications_tenant_status", "tenant_id", "status"),
        Index("ix_person_applications_tenant_person_id", "tenant_id", "person_id"),
        Index("ix_person_applications_tenant_application_type", "tenant_id", "application_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    application_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="DRIVER", index=True
    )
    requested_role_code: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="DRIVER",
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarded_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: pending | pending_downstream | complete (people-level setup lifecycle; not the same as status).
    setup_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending", default="pending")
    #: Current queue / ownership (submitted|processing|hr_payroll|complete|rejected); not historical truth.
    current_workflow_lane: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="processing", default="processing"
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: Frozen copy of structured intake when applicant submitted (evidence; not overwritten by admin edits).
    intake_submitted_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: Append-only audit entries: [{at, by_user_id, changed_keys: [...]}, ...]
    intake_review_audit: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    access_tokens: Mapped[list["ApplicationAccessToken"]] = relationship(
        "ApplicationAccessToken",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
