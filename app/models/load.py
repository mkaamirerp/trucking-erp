from __future__ import annotations

from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Load(Base):
    __tablename__ = "loads"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    load_number: Mapped[str] = mapped_column(String(50), nullable=False)
    broker_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("brokers.id", ondelete="RESTRICT"), nullable=True, index=True)
    driver_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True, index=True)
    pickup_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    pickup_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    miles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    broker = relationship("Broker", back_populates="loads")
    driver = relationship("Driver", back_populates="loads")
