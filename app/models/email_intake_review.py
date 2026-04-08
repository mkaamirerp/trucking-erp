"""Structured intake review state + append-only events (tenant DB; email thread scope)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmailIntakeReview(Base):
    """At most one active review row per email thread (intake / broker review spine)."""

    __tablename__ = "email_intake_reviews"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_thread_id", name="uq_email_intake_reviews_tenant_thread"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email_thread_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Stable machine code (first segment of ``routing_reason`` today); not a sentence.
    primary_code: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Parsed ``|k=v`` tails, ``routing_reason_full``, etc.
    detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: open | claimed | resolved | dismissed
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="open")
    claimed_by_tenant_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant_users.id", ondelete="SET NULL"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_routing_reason_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EmailIntakeReviewEvent(Base):
    """Append-only audit trail for intake review workflow."""

    __tablename__ = "email_intake_review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email_intake_review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_intake_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    #: system | tenant_user | platform_user
    actor_kind: Mapped[str] = mapped_column(String(24), nullable=False, server_default="system")
    actor_tenant_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant_users.id", ondelete="SET NULL"), nullable=True
    )
    actor_platform_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    old_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
