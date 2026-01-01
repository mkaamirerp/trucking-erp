from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CHAR,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    JSON,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base
from app.models.enums import PayDocumentType, PayRunStatus, PayoutStatus, SourceType, WorkerType


class PayPeriod(Base):
    __tablename__ = "pay_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default="OPEN")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PayRun(Base):
    __tablename__ = "pay_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pay_periods.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    pay_document_type: Mapped[PayDocumentType] = mapped_column(
        SAEnum(PayDocumentType, name="pay_document_type", native_enum=True), nullable=False
    )
    worker_type_snapshot: Mapped[WorkerType] = mapped_column(
        SAEnum(WorkerType, name="worker_type", native_enum=True), nullable=False
    )
    base_currency_snapshot: Mapped[str] = mapped_column(CHAR(length=3), nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PayRunStatus] = mapped_column(
        SAEnum(PayRunStatus, name="pay_run_status", native_enum=True),
        nullable=False,
        default=PayRunStatus.DRAFT,
        server_default=PayRunStatus.DRAFT.value,
    )
    payout_status: Mapped[PayoutStatus] = mapped_column(
        SAEnum(PayoutStatus, name="payout_status", native_enum=True),
        nullable=False,
        default=PayoutStatus.UNPAID,
        server_default=PayoutStatus.UNPAID.value,
    )
    calculation_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PayRunItem(Base):
    __tablename__ = "pay_run_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    pay_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", native_enum=True), nullable=False
    )
    charge_category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("charge_categories.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    amount_signed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(length=3), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PayProfile(Base):
    __tablename__ = "pay_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    driver_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    pay_type: Mapped[str] = mapped_column(String(20), nullable=False)  # per_mile, hourly, percentage, salary
    rate_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    rate_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)  # mile, hour, percent, salary
    percentage_basis_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD", server_default="USD")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    effective_start: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    effective_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PayEntry(Base):
    __tablename__ = "pay_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pay_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    driver_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pay_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )

    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MILES, HOURS, GROSS, ADJUSTMENT, DEDUCTION
    reference_code: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rate_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
