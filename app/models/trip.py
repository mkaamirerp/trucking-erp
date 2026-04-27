"""Trip container (Phase 1): operational row + trip↔load membership. Writer remains dispatch_trips + loads."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Trip(Base):
    """Long-term trip container. Phase 1: backfilled from dispatch_trips; legacy_dispatch_trip_id links rows."""

    __tablename__ = "trips"
    __table_args__ = (
        Index("ix_trips_tenant_trip_number", "tenant_id", "trip_number", unique=True),
        Index("ix_trips_tenant_id", "tenant_id"),
        Index("ix_trips_tenant_id_status", "tenant_id", "status"),
        Index("ix_trips_tenant_id_job_type", "tenant_id", "job_type"),
        Index("ix_trips_tenant_id_driver_id", "tenant_id", "driver_id"),
        Index("ix_trips_tenant_id_truck_id", "tenant_id", "truck_id"),
        Index("ix_trips_tenant_id_trailer_id", "tenant_id", "trailer_id"),
        # Partial unique: one legacy id when set (see migration; matches DB).
        Index(
            "ix_trips_legacy_dispatch_trip_id",
            "legacy_dispatch_trip_id",
            unique=True,
            postgresql_where=text("legacy_dispatch_trip_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    trip_number: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trailer_move_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legacy_dispatch_trip_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dispatch_trips.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    driver_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    truck_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trucks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trailer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trailers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    trip_loads = relationship("TripLoad", back_populates="trip")


class TripLoad(Base):
    """Load membership in a trip. Composite FKs for tenant isolation."""

    __tablename__ = "trip_loads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_trip_loads_load_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_trip_loads_tenant_trip_id", "tenant_id", "trip_id"),
        Index("ix_trip_loads_tenant_load_id", "tenant_id", "load_id"),
        Index("ix_trip_loads_tenant_status_within", "tenant_id", "status_within_trip"),
        Index(
            "uq_trip_loads_active_membership",
            "tenant_id",
            "trip_id",
            "load_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    trip_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    load_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status_within_trip: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    sequence_hint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    trip = relationship("Trip", back_populates="trip_loads")
