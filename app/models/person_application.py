from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PersonApplication(Base):
    __tablename__ = "person_applications"
    __table_args__ = (
        Index("ix_person_applications_tenant_id", "tenant_id"),
        Index("ix_person_applications_tenant_status", "tenant_id", "status"),
        Index("ix_person_applications_tenant_person_id", "tenant_id", "person_id"),
        ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_person_applications_tenant_person_to_people",
            ondelete="SET NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Intake fields (keep nullable for drafts)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flexible JSON payload (optional)
    intake_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    files: Mapped[list["PersonApplicationFile"]] = relationship(
        "PersonApplicationFile",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    requests: Mapped[list["PersonApplicationRequest"]] = relationship(
        "PersonApplicationRequest",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    access_tokens: Mapped[list["ApplicationAccessToken"]] = relationship(
        "ApplicationAccessToken",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
