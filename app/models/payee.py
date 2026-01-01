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
    UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import (
    CalcMethod,
    EscrowEntryType,
    EscrowRuleType,
    Frequency,
    GrossCalcType,
    MileSource,
    OverrideType,
    PayDocumentType,
    PayMileMode,
    PayRunStatus,
    PayeeType,
    PayoutPaymentStatus,
    PayoutStatus,
    Responsibility,
    SettlementFrequency,
    SourceType,
    WorkerType,
)


class Payee(Base):
    __tablename__ = "payees"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_type: Mapped[PayeeType] = mapped_column(SAEnum(PayeeType, name="payee_type", native_enum=True), nullable=False)
    worker_type: Mapped[WorkerType] = mapped_column(SAEnum(WorkerType, name="worker_type", native_enum=True), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    carrier_mc_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    carrier_dot_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    incorporation_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id_last4: Mapped[str | None] = mapped_column(CHAR(length=4), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_number", name="uq_employee_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    employee_number: Mapped[str] = mapped_column(Text, nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )

    @property
    def employee_code(self) -> str:
        # Legacy alias surfaced in API responses
        return self.employee_number


class CompensationProfile(Base):
    __tablename__ = "compensation_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    worker_type_snapshot: Mapped[WorkerType] = mapped_column(
        SAEnum(WorkerType, name="worker_type", native_enum=True), nullable=False
    )
    gross_calc_type: Mapped[GrossCalcType] = mapped_column(
        SAEnum(GrossCalcType, name="gross_calc_type", native_enum=True), nullable=False
    )

    percent_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    cpm_loaded: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    cpm_empty: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    salary_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    flat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    dispatch_fee_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    dispatch_fee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0, server_default="0.0000")
    dispatch_fee_basis: Mapped[str] = mapped_column(Text, nullable=False, default="GROSS", server_default="GROSS")

    settlement_frequency: Mapped[SettlementFrequency] = mapped_column(
        SAEnum(SettlementFrequency, name="settlement_frequency", native_enum=True),
        nullable=False,
        default=SettlementFrequency.BIWEEKLY,
        server_default=SettlementFrequency.BIWEEKLY.value,
    )
    allow_negative_settlement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class TenantMileagePolicy(Base):
    __tablename__ = "tenant_mileage_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    default_mile_source: Mapped[MileSource] = mapped_column(
        SAEnum(MileSource, name="mile_source", native_enum=True),
        nullable=False,
        default=MileSource.ADDRESS_TO_ADDRESS,
        server_default=MileSource.ADDRESS_TO_ADDRESS.value,
    )
    pay_mile_mode: Mapped[PayMileMode] = mapped_column(
        SAEnum(PayMileMode, name="pay_mile_mode", native_enum=True),
        nullable=False,
        default=PayMileMode.ALL_MILES,
        server_default=PayMileMode.ALL_MILES.value,
    )
    empty_mile_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    allow_manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    override_requires_reason: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class ChargeCategory(Base):
    __tablename__ = "charge_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_charge_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_responsibility: Mapped[Responsibility] = mapped_column(
        SAEnum(Responsibility, name="responsibility", native_enum=True),
        nullable=False,
        default=Responsibility.WORKER,
        server_default=Responsibility.WORKER.value,
    )
    requires_document: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class CompProfileChargeRule(Base):
    __tablename__ = "comp_profile_charge_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compensation_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compensation_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    charge_category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("charge_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    responsibility: Mapped[Responsibility] = mapped_column(
        SAEnum(Responsibility, name="responsibility", native_enum=True), nullable=False
    )
    calc_method: Mapped[CalcMethod] = mapped_column(SAEnum(CalcMethod, name="calc_method", native_enum=True), nullable=False)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    flat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    frequency: Mapped[Frequency] = mapped_column(
        SAEnum(Frequency, name="frequency", native_enum=True),
        nullable=False,
        default=Frequency.ONE_TIME,
        server_default=Frequency.ONE_TIME.value,
    )
    cap_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    default_apply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class EscrowAccount(Base):
    __tablename__ = "escrow_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int] = mapped_column(Integer, ForeignKey("payees.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    target_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0.00"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class EscrowRule(Base):
    __tablename__ = "escrow_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    escrow_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("escrow_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_type: Mapped[EscrowRuleType] = mapped_column(
        SAEnum(EscrowRuleType, name="escrow_rule_type", native_enum=True), nullable=False
    )
    weeks_to_hold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_per_period: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class EscrowLedgerEntry(Base):
    __tablename__ = "escrow_ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    escrow_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("escrow_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pay_runs.id", ondelete="SET NULL"), nullable=True)
    entry_type: Mapped[EscrowEntryType] = mapped_column(
        SAEnum(EscrowEntryType, name="escrow_entry_type", native_enum=True), nullable=False
    )
    amount_signed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class PayeeBalance(Base):
    __tablename__ = "payee_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int] = mapped_column(Integer, ForeignKey("payees.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of_pay_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pay_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    balance_signed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class PayRunOverride(Base):
    __tablename__ = "pay_run_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False)
    override_type: Mapped[OverrideType] = mapped_column(
        SAEnum(OverrideType, name="override_type", native_enum=True), nullable=False
    )
    before_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class PayDocument(Base):
    __tablename__ = "pay_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False)
    payee_id: Mapped[int] = mapped_column(Integer, ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False)
    document_type: Mapped[PayDocumentType] = mapped_column(
        SAEnum(PayDocumentType, name="pay_document_type", native_enum=True), nullable=False
    )
    file_storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    generated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PayoutRail(Base):
    __tablename__ = "payout_rails"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    supports_connector: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class TenantPayoutRailSetting(Base):
    __tablename__ = "tenant_payout_rail_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "payout_rail_id", name="uq_tenant_rail"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payout_rail_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payout_rails.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class PayeePayoutPreference(Base):
    __tablename__ = "payee_payout_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int] = mapped_column(Integer, ForeignKey("payees.id", ondelete="CASCADE"), nullable=False, index=True)
    payout_rail_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payout_rails.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class PayRunPayment(Base):
    __tablename__ = "pay_run_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False)
    payee_id: Mapped[int] = mapped_column(Integer, ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payout_rail_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payout_rails.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[PayoutPaymentStatus] = mapped_column(
        SAEnum(PayoutPaymentStatus, name="payout_payment_status", native_enum=True), nullable=False
    )
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )


class TenantBankConnector(Base):
    __tablename__ = "tenant_bank_connectors"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uq_tenant_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DISCONNECTED", server_default="DISCONNECTED")
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    secrets_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default="now()"
    )
