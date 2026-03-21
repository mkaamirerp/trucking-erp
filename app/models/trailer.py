"""Trailer model for inventory-only fleet management."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Trailer(Base):
    __tablename__ = "trailers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_number", name="uq_trailers_tenant_unit_number"),
        ForeignKeyConstraint(
            ["tenant_id", "owner_person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_trailers_owner_person_to_people",
            ondelete="SET NULL",
        ),
        Index("ix_trailers_tenant_id", "tenant_id"),
        Index("ix_trailers_status", "status"),
        Index("ix_trailers_ownership_type", "ownership_type"),
        Index("ix_trailers_unit_number", "tenant_id", "unit_number"),
        Index("ix_trailers_plate_number", "plate_number"),
        # Partial unique on vin: uq_trailers_tenant_vin created in migration (WHERE vin IS NOT NULL)
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    vin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plate_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plate_region: Mapped[str | None] = mapped_column(String(20), nullable=True)

    trailer_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="dry_van")
    length_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_axles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gvwr_lbs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    door_type: Mapped[str | None] = mapped_column(String(30), nullable=True)

    reefer_make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reefer_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reefer_serial: Mapped[str | None] = mapped_column(String(100), nullable=True)

    ownership_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="company")
    owner_person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    insurance_carrier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insurance_policy_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    insurance_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
