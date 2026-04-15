"""Phase 3A: tenant-scoped driver operational extension (not pay, not dispatch roster truth)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.person import Person


class DriverPersonExtension(Base):
    """Role-attached driver configuration: one row per (tenant_id, person_id).

    Source of truth for these fields stays in this table — not in ``people`` or applications.
    People workspace PATCH ``/people/{id}/driver-role-configuration`` is the maintained correction path;
    onboarding remains workflow-only.
    """

    __tablename__ = "driver_person_extensions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_driver_person_extensions_tenant_person_to_people",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "person_id", name="uq_driver_person_extensions_tenant_person"),
        Index("ix_driver_person_extensions_tenant_id", "tenant_id"),
        Index("ix_driver_person_extensions_person_id", "person_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    employment_relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    driver_operating_subtype: Mapped[str] = mapped_column(String(50), nullable=False)
    is_team_driver: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    team_role_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provides_own_truck: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    provides_own_trailer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    equipment_contribution_type: Mapped[str] = mapped_column(String(50), nullable=False)
    insurance_commercial_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    person: Mapped["Person"] = relationship("Person", back_populates="driver_person_extension")
