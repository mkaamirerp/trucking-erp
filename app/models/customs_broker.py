"""Customs broker master data and per-load frozen customs snapshot."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CustomsBroker(Base):
    __tablename__ = "customs_brokers"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_customs_brokers_tenant_id_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admin_area: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone_primary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fax: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generic_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    contacts = relationship(
        "CustomsBrokerContact",
        back_populates="customs_broker",
        cascade="all, delete-orphan",
    )
    loads = relationship("Load", back_populates="customs_broker")


class CustomsBrokerContact(Base):
    __tablename__ = "customs_broker_contacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customs_broker_id"],
            ["customs_brokers.tenant_id", "customs_brokers.id"],
            ondelete="CASCADE",
            name="fk_customs_broker_contacts_broker_tenant",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customs_broker_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fax: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customs_broker = relationship("CustomsBroker", back_populates="contacts")


class LoadCustomsSnapshot(Base):
    """One row per load: frozen customs broker fields at document snapshot confirmation."""

    __tablename__ = "load_customs_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            ondelete="CASCADE",
            name="fk_load_customs_snapshots_load_tenant",
        ),
        PrimaryKeyConstraint("load_id", name="pk_load_customs_snapshots"),
    )

    load_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    legal_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admin_area_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country_code_snapshot: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone_primary_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_secondary_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fax_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generic_email_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website_url_snapshot: Mapped[str | None] = mapped_column(String(512), nullable=True)
    customs_broker_id_at_confirm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    load = relationship(
        "Load",
        back_populates="customs_snapshot",
        foreign_keys=[load_id, tenant_id],
    )
