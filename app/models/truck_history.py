"""Effective-dated truck unit-number and ownership history (Fuel Segment 3).

These are fleet historical facts used by Fuel resolution. Current
`trucks.unit_number` / `trucks.ownership_type` are not resolution fallbacks.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TruckUnitNumberHistory(Base):
    """Effective-dated unit number for a permanent truck_id."""

    __tablename__ = "truck_unit_number_history"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_truck_unit_number_history_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_truck_unit_number_history_truck_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_truck_unit_number_history_tenant_id", "tenant_id"),
        Index("ix_truck_unit_number_history_tenant_truck", "tenant_id", "truck_id"),
        Index(
            "ix_truck_unit_number_history_tenant_unit_from",
            "tenant_id",
            "unit_number",
            "effective_from",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    truck_id: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    # Half-open interval [effective_from, effective_to)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TruckOwnershipHistory(Base):
    """Effective-dated truck ownership / O-O payee responsibility."""

    __tablename__ = "truck_ownership_history"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_truck_ownership_history_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_truck_ownership_history_truck_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_truck_ownership_history_tenant_id", "tenant_id"),
        Index("ix_truck_ownership_history_tenant_truck", "tenant_id", "truck_id"),
        Index(
            "ix_truck_ownership_history_tenant_truck_from",
            "tenant_id",
            "truck_id",
            "effective_from",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    truck_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ownership_type: Mapped[str] = mapped_column(String(30), nullable=False)
    owner_operator_payee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
