"""Immutable revised rate confirmations. Only is_current may change, true to false."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoadRateConfirmationRevision(Base):
    __tablename__ = "load_rate_confirmation_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            ondelete="RESTRICT",
            name="fk_load_rc_revisions_load",
        ),
        UniqueConstraint(
            "tenant_id",
            "load_id",
            "revision_number",
            name="uq_load_rc_revisions_tenant_load_number",
        ),
        UniqueConstraint(
            "tenant_id",
            "load_id",
            "file_sha256",
            name="uq_load_rc_revisions_tenant_load_sha",
        ),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_load_rc_revisions_number_positive",
        ),
        Index(
            "uq_load_rc_revisions_one_current",
            "tenant_id",
            "load_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    load_id: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_parse_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    accepted_changes_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    compare_notices_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    accepted_by_platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
