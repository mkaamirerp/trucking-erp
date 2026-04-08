"""Broker master data: firm, contacts, domains, aliases, known senders (ingestion).

Customs brokers are a separate module (`customs_broker`). Loads keep broker snapshots
immutable on historical rows; this model is operational / booking broker master only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    #: Legacy list/sort key; kept in sync with display/ legal names in application layer.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Motor carrier (MC) number historically; kept alongside dot_number.
    mc_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dot_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_secondary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_postal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    classification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    #: When true, intake resolver excludes this broker (messages route to review if no other match).
    intake_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    #: System-created broker stub metadata (global reference / auto-create phases).
    auto_created: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    auto_create_origin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auto_create_needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    #: Logical link to platform.global_booking_brokers.id (no cross-DB FK).
    platform_global_broker_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    loads = relationship("Load", back_populates="broker")
    contacts = relationship("BrokerContact", back_populates="broker", cascade="all, delete-orphan")
    domains = relationship("BrokerDomain", back_populates="broker", cascade="all, delete-orphan")
    aliases = relationship("BrokerAlias", back_populates="broker", cascade="all, delete-orphan")
    known_senders = relationship("BrokerKnownSender", back_populates="broker", cascade="all, delete-orphan")


class BrokerContact(Base):
    """Agent/person under a broker."""

    __tablename__ = "broker_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    broker_id: Mapped[int] = mapped_column(Integer, ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fax: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    broker = relationship("Broker", back_populates="contacts")


class BrokerDomain(Base):
    """Email domain for intake matching."""

    __tablename__ = "broker_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    broker_id: Mapped[int] = mapped_column(Integer, ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    broker = relationship("Broker", back_populates="domains")


class BrokerAlias(Base):
    """Normalized alias for strict intake matching."""

    __tablename__ = "broker_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    broker_id: Mapped[int] = mapped_column(Integer, ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="display")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    broker = relationship("Broker", back_populates="aliases")


class BrokerKnownSender(Base):
    """Exact From-address match for email ingestion (normalized lowercase email)."""

    __tablename__ = "broker_known_senders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    broker_id: Mapped[int] = mapped_column(Integer, ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    broker = relationship("Broker", back_populates="known_senders")
