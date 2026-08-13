"""Append-only load custody events (continuity truth). Slice 1: foundation + bootstrap only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoadCustodyEvent(Base):
    __tablename__ = "load_custody_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_custody_events_load_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    load_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    custody_owner_after: Mapped[str] = mapped_column(String(32), nullable=False)
    placement_after: Mapped[str] = mapped_column(String(32), nullable=False)
    trip_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    terminal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("terminals.id", ondelete="SET NULL"), nullable=True
    )
    trailer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trailers.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
