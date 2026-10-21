"""Future Movement Plan — §9A pre-Trip planning (not a Trip)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FutureMovementPlan(Base):
    __tablename__ = "future_movement_plans"
    __table_args__ = (
        Index("ix_fmp_tenant_status", "tenant_id", "status"),
        Index(
            "uq_fmp_tenant_conversion_idem",
            "tenant_id",
            "conversion_idempotency_key",
            unique=True,
            postgresql_where=text("conversion_idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="manual")
    pickup_terminal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("terminals.id", ondelete="RESTRICT"), nullable=True
    )
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_completion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True
    )
    truck_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trucks.id", ondelete="SET NULL"), nullable=True
    )
    trailer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trailers.id", ondelete="SET NULL"), nullable=True
    )
    converted_trip_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trips.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    conversion_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    lines = relationship("FutureMovementPlanLoad", back_populates="plan", cascade="all, delete-orphan")


class FutureMovementPlanLoad(Base):
    __tablename__ = "future_movement_plan_loads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_fmpl_load_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_fmpl_tenant_plan", "tenant_id", "plan_id"),
        Index("ix_fmpl_tenant_load", "tenant_id", "load_id"),
        Index(
            "uq_fmpl_one_open_reservation_per_load",
            "tenant_id",
            "load_id",
            unique=True,
            postgresql_where=text("released_at IS NULL AND converted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("future_movement_plans.id", ondelete="CASCADE"), nullable=False
    )
    load_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sequence_hint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inbound_trip_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    plan = relationship("FutureMovementPlan", back_populates="lines")
