"""Per-tenant monthly counters for internal load_number minting (Task 14)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TenantLoadNumberPeriod(Base):
    """One row per tenant per YYYY-MM period (company TZ at mint time)."""

    __tablename__ = "tenant_load_number_periods"
    __table_args__ = (
        CheckConstraint(
            "period ~ '^[0-9]{4}-[0-9]{2}$'",
            name="ck_tenant_load_number_periods_period",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    next_numeric: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
