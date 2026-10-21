"""Operational dispatch instructions — not custody, not Load.status."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoadDispatchInstruction(Base):
    __tablename__ = "load_dispatch_instructions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_ldi_load_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_ldi_tenant_load", "tenant_id", "load_id"),
        Index("ix_ldi_tenant_inbound_trip", "tenant_id", "inbound_trip_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    load_id: Mapped[int] = mapped_column(Integer, nullable=False)
    inbound_trip_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    terminal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("terminals.id", ondelete="SET NULL"), nullable=True
    )
    instruction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
