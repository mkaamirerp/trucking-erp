"""People-first models: Person, PersonRole, DriverProfile. Used for driver onboarding (no writes to drivers)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        Index("ix_people_tenant_id", "tenant_id"),
        Index("ix_people_tenant_id_email", "tenant_id", "email"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    onboarding_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    roles: Mapped[list["PersonRole"]] = relationship(
        "PersonRole",
        back_populates="person",
        cascade="all, delete-orphan",
    )
    driver_profile: Mapped["DriverProfile | None"] = relationship(
        "DriverProfile",
        back_populates="person",
        uselist=False,
        cascade="all, delete-orphan",
    )


class PersonRole(Base):
    __tablename__ = "person_roles"
    __table_args__ = (
        Index("ix_person_roles_tenant_id", "tenant_id"),
        Index("ix_person_roles_person_id", "person_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_code: Mapped[str] = mapped_column(String(50), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    person: Mapped["Person"] = relationship("Person", back_populates="roles")


class DriverProfile(Base):
    __tablename__ = "driver_profiles"
    __table_args__ = (
        Index("ix_driver_profiles_tenant_id", "tenant_id"),
        Index("ix_driver_profiles_person_id", "person_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    person: Mapped["Person"] = relationship("Person", back_populates="driver_profile")
