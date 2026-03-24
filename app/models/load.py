"""Load model for dispatch. V1 statuses: draft, ready; operational: unassigned, assigned, dispatched, etc."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Load(Base):
    __tablename__ = "loads"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    load_number: Mapped[str] = mapped_column(String(50), nullable=False)
    broker_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("brokers.id", ondelete="RESTRICT"), nullable=True, index=True)
    broker_contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("broker_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    driver_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True, index=True)
    truck_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("trucks.id", ondelete="SET NULL"), nullable=True, index=True)
    trailer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("trailers.id", ondelete="SET NULL"), nullable=True, index=True)

    # Broker/contact snapshots (load-specific copies; edits don't change master)
    broker_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    broker_contact_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    broker_contact_phone_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    broker_contact_extension_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    broker_contact_email_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    broker_load_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    equipment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trailer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trailer_size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    commodity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hazmat_flag: Mapped[bool] = mapped_column(Boolean, nullable=True, server_default="false")
    temperature_requirement: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pallet_case_count: Mapped[str | None] = mapped_column(String(50), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    customer_rate: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    miles: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    current_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    broker = relationship("Broker", back_populates="loads")
    broker_contact = relationship("BrokerContact", backref="loads")
    driver = relationship("Driver", back_populates="loads")
    truck = relationship("Truck", backref="loads")
    trailer = relationship("Trailer", backref="loads")
    stops = relationship("LoadStop", back_populates="load", order_by="LoadStop.sequence", cascade="all, delete-orphan")
    notes_rel = relationship("LoadNote", back_populates="load", order_by="LoadNote.created_at", cascade="all, delete-orphan")


class LoadStop(Base):
    """Stop on a load. stop_type: PICKUP or DROP. sequence for route order."""

    __tablename__ = "load_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    load_id: Mapped[int] = mapped_column(Integer, ForeignKey("loads.id", ondelete="CASCADE"), nullable=False, index=True)
    stop_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    facility_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state_or_province: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    appointment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    appointment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    appointment_time_text: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    commodity_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    load = relationship("Load", back_populates="stops")
    actions = relationship("LoadStopAction", back_populates="load_stop", cascade="all, delete-orphan")


class LoadStopAction(Base):
    """Stop-level actions: live_load, drop_trailer, hook_trailer, relay, yard_move."""
    __tablename__ = "load_stop_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    load_stop_id: Mapped[int] = mapped_column(Integer, ForeignKey("load_stops.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    load_stop = relationship("LoadStop", back_populates="actions")


class LoadNote(Base):
    __tablename__ = "load_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    load_id: Mapped[int] = mapped_column(Integer, ForeignKey("loads.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    load = relationship("Load", back_populates="notes_rel")
