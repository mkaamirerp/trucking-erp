"""Canonical dispatch trip rows (trip_number owner). See docs/DISPATCH_TRIP_NUMBER_RULE.md."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TenantDispatchNumbering(Base):
    """One row per tenant: locked prefix + monotonic numeric (same transaction as allocation)."""

    __tablename__ = "tenant_dispatch_numbering"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_number_prefix: Mapped[str] = mapped_column(String(16), nullable=False, server_default="")
    prefix_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_numeric: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="10001")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DispatchTrip(Base):
    """Canonical trip_number and lifecycle. Exactly one of load_id / trailer_move_id (v1: freight load only)."""

    __tablename__ = "dispatch_trips"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_dispatch_trips_load_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(CASE WHEN load_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN trailer_move_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_dispatch_trips_exactly_one_target",
        ),
        CheckConstraint(
            "(job_type = 'freight_load' AND load_id IS NOT NULL AND trailer_move_id IS NULL) OR "
            "(job_type = 'trailer_move' AND trailer_move_id IS NOT NULL AND load_id IS NULL)",
            name="ck_dispatch_trips_job_type_matches_fk",
        ),
        Index("ix_dispatch_trips_tenant_status", "tenant_id", "status"),
        Index("ix_dispatch_trips_tenant_trip_number", "tenant_id", "trip_number", unique=True),
        Index(
            "uq_dispatch_trips_tenant_load_active",
            "tenant_id",
            "load_id",
            unique=True,
            postgresql_where=text("status = 'active' AND load_id IS NOT NULL"),
        ),
        Index(
            "uq_dispatch_trips_tenant_trailer_move_active",
            "tenant_id",
            "trailer_move_id",
            unique=True,
            postgresql_where=text("status = 'active' AND trailer_move_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    trip_number: Mapped[str] = mapped_column(String(32), nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    load_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trailer_move_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    load = relationship("Load", back_populates="dispatch_trips")
