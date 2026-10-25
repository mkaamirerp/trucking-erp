"""Tenant equipment facts (schema only; no runtime writers at this checkpoint).

Defaults are preferences. Current attachments are *confirmed physical state*,
not inferred from planned/assigned/in-progress/completed Trips.
A future service must update current state + audit_events in one transaction.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer,
    String, text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DriverEquipmentDefault(Base):
    __tablename__ = "driver_equipment_defaults"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "driver_id"],
            ["drivers.tenant_id", "drivers.id"],
            name="fk_equipment_defaults_driver_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "default_truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_equipment_defaults_truck_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "equipment_binding_mode IN ('dedicated', 'owner_bound', 'shift_based', 'pooled')",
            name="ck_equipment_defaults_binding_mode",
        ),
        Index(
            "ix_driver_equipment_defaults_tenant_truck",
            "tenant_id", "default_truck_id",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    default_truck_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equipment_binding_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pooled"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )


class EquipmentCurrentAttachment(Base):
    __tablename__ = "equipment_current_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_equipment_attachments_truck_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "driver_id"],
            ["drivers.tenant_id", "drivers.id"],
            name="fk_equipment_attachments_driver_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "trailer_id"],
            ["trailers.tenant_id", "trailers.id"],
            name="fk_equipment_attachments_trailer_tenant",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_equipment_current_tenant_driver",
            "tenant_id", "driver_id", unique=True,
            postgresql_where=text("driver_id IS NOT NULL"),
        ),
        Index(
            "uq_equipment_current_tenant_trailer",
            "tenant_id", "trailer_id", unique=True,
            postgresql_where=text("trailer_id IS NOT NULL"),
        ),
        CheckConstraint(
            "version >= 1", name="ck_equipment_attachments_version_positive"
        ),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    truck_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trailer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
