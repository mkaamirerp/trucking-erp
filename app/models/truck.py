"""Truck model for inventory-only fleet management."""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Truck(Base):
    __tablename__ = "trucks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_number", name="uq_trucks_tenant_unit_number"),
        UniqueConstraint("tenant_id", "vin", name="uq_trucks_tenant_vin"),
        ForeignKeyConstraint(
            ["tenant_id", "owner_person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_trucks_owner_person_to_people",
            ondelete="SET NULL",
        ),
        Index("ix_trucks_tenant_id", "tenant_id"),
        Index("ix_trucks_status", "status"),
        Index("ix_trucks_ownership_type", "ownership_type"),
        Index("ix_trucks_unit_number", "tenant_id", "unit_number"),
        Index("ix_trucks_vin", "tenant_id", "vin"),
        Index("ix_trucks_plate_number", "plate_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    vin: Mapped[str] = mapped_column(String(50), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plate_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plate_region: Mapped[str | None] = mapped_column(String(20), nullable=True)

    ownership_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="company")
    owner_person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    engine_make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    engine_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    engine_serial: Mapped[str | None] = mapped_column(String(100), nullable=True)
    horsepower: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    transmission: Mapped[str | None] = mapped_column(String(30), nullable=True)
    num_axles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gvwr_lbs: Mapped[int | None] = mapped_column(Integer, nullable=True)

    odometer_at_purchase: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_odometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    odometer_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
