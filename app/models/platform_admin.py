"""Platform admin (control-plane) model. Separate from tenant auth."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PlatformAdmin(Base):
    """
    Dedicated platform admin table. Control-plane auth only.
    Do not use tenant membership or tenant roles for platform admin.
    """

    __tablename__ = "platform_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("platform_admins.id", ondelete="SET NULL"), nullable=True, index=True
    )

    platform_user = relationship("PlatformUser", backref="platform_admin_record", foreign_keys=[platform_user_id])
