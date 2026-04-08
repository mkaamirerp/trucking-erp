"""Platform-owned global booking-broker reference (read-only for tenants; intake matching only)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class GlobalBookingBroker(Base):
    """Canonical broker identity for day-one intake when tenant workspace has no match."""

    __tablename__ = "global_booking_brokers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Operational list key; kept in sync with display/legal in admin flows.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mc_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dot_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Ontario/CA CVOR — 9 digits stored (same convention as platform company profile).
    cvor_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: pending | approved — resolver uses approved only.
    canonical_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    #: Set when this row is the **loser** in a completed global merge (survivor id). Immutable in contract after set.
    merged_into_global_broker_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("global_booking_brokers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: When ``merged_into_global_broker_id`` was recorded (merge execution; Slice 4+).
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    domains = relationship("GlobalBookingBrokerDomain", back_populates="broker", cascade="all, delete-orphan")
    known_senders = relationship("GlobalBookingBrokerKnownSender", back_populates="broker", cascade="all, delete-orphan")
    aliases = relationship("GlobalBookingBrokerAlias", back_populates="broker", cascade="all, delete-orphan")


class GlobalBookingBrokerDomain(Base):
    __tablename__ = "global_booking_broker_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    global_broker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    broker = relationship("GlobalBookingBroker", back_populates="domains")


class GlobalBookingBrokerKnownSender(Base):
    __tablename__ = "global_booking_broker_known_senders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    global_broker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    broker = relationship("GlobalBookingBroker", back_populates="known_senders")


class GlobalBookingBrokerAlias(Base):
    __tablename__ = "global_booking_broker_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    global_broker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    broker = relationship("GlobalBookingBroker", back_populates="aliases")


class GlobalBookingBrokerAuditEvent(Base):
    """Append-only promotion / admin audit for global booking brokers (platform scope)."""

    __tablename__ = "global_booking_broker_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    global_broker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GlobalBookingBrokerDuplicateCandidate(Base):
    """Operator-reviewed possible duplicate pair (no automated merge)."""

    __tablename__ = "global_booking_broker_duplicate_candidates"
    __table_args__ = (
        UniqueConstraint("broker_id_low", "broker_id_high", name="uq_global_booking_broker_dup_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_id_low: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    broker_id_high: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: JSON array of stable signal strings, e.g. ``shared_mc_number``, ``shared_domain:example.com``.
    match_signals: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    #: ``open`` | ``dismissed`` | ``acknowledged`` — terminal reviews stay until next manual reopen (future).
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="open")
    duplicate_review_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GlobalBookingBrokerMergePreview(Base):
    """Stored merge preview (platform); optional row for Slice 5 execute idempotency."""

    __tablename__ = "global_booking_broker_merge_previews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_global_broker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False
    )
    survivor_global_broker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("global_booking_brokers.id", ondelete="CASCADE"), nullable=False
    )
    duplicate_candidate_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("global_booking_broker_duplicate_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
