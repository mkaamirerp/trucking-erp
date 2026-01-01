from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("slug", name="uq_tenants_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
