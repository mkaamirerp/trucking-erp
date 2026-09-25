"""Fuel/Card tenant models.

Segment 0A: provider connections.
Segment 1: source batches + canonical transactions (schema foundation only).
Segment 2: provider control totals as reconciliation evidence, not purchases.
Segment 3: effective-dated card/account assignment history.
Segment 4: effective-dated O/O fuel pricing rules + transaction provenance.
Segment 8: source review queue — extraction corrections + review provenance.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FuelProviderConnection(Base):
    """Tenant-side Fuel provider connection metadata. Secrets live in platform DB.

    `tenant_id` is required on this per-tenant-database table because TruckERP
    data-plane convention is composite tenant isolation `(tenant_id, id)` on
    every tenant table (same pattern as `people`, `loads`, `tenant_email_mailboxes`).
    It is not a claim that this row lives in the platform DB. Queries still
    filter `tenant_id` as defense-in-depth if the wrong tenant engine is used,
    and composite unique/FK patterns stay consistent with adjacent tenant models.
    """

    __tablename__ = "fuel_provider_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fuel_provider_connections_tenant_id_id"),
        CheckConstraint(
            "jsonb_typeof(config_json) = 'object'",
            name="ck_fuel_provider_connections_config_json_object",
        ),
        Index("ix_fuel_provider_connections_tenant_id", "tenant_id"),
        Index("ix_fuel_provider_connections_tenant_provider", "tenant_id", "provider_code"),
        Index(
            "ix_fuel_provider_connections_tenant_credential_ref",
            "tenant_id",
            "credential_ref",
            unique=True,
            postgresql_where=text("credential_ref IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_code: Mapped[str] = mapped_column(String(40), nullable=False)
    connection_method: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    credential_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sync_frequency: Mapped[str | None] = mapped_column(String(40), nullable=True)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_sync_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_test_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class FuelSourceBatch(Base):
    """One provider statement/file/feed/manual intake batch.

    Design name: fuel_card_import_batches. Physical name: fuel_source_batches
    (consistent with fuel_provider_connections). Provider control totals live
    only on fuel_source_controls; this batch table does not store a second
    authoritative control-totals representation.
    """

    __tablename__ = "fuel_source_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fuel_source_batches_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "provider_connection_id"],
            ["fuel_provider_connections.tenant_id", "fuel_provider_connections.id"],
            name="fk_fuel_source_batches_provider_connection_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_type IN ('PDF', 'STRUCTURED_FILE', 'SFTP_FILE', 'MANUAL_DRIVER', 'API')",
            name="ck_fuel_source_batches_source_type",
        ),
        Index("ix_fuel_source_batches_tenant_id", "tenant_id"),
        Index("ix_fuel_source_batches_tenant_provider", "tenant_id", "provider_code"),
        Index(
            "ix_fuel_source_batches_tenant_source_hash",
            "tenant_id",
            "source_hash",
            unique=True,
            postgresql_where=text("source_hash IS NOT NULL"),
        ),
        Index("ix_fuel_source_batches_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_code: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)

    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    source_storage_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    remote_timestamp: Mapped[str | None] = mapped_column(String(128), nullable=True)

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    parser_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_profile_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    layout_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="UPLOADED")
    review_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    review_started_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    problem_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class FuelTransaction(Base):
    """Canonical Fuel/Card transaction. Provider facts stay separate from resolution.

    Three identities:
    - id (+ tenant_id): TruckERP canonical transaction identity
    - provider_transaction_identity: provider auth/txn number when supplied (not PK)
    - (batch_id, source_row_order) / source_row_id: provider source-row identity
    """

    __tablename__ = "fuel_transactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fuel_transactions_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "source_row_order",
            name="uq_fuel_transactions_tenant_batch_source_row_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["fuel_source_batches.tenant_id", "fuel_source_batches.id"],
            name="fk_fuel_transactions_batch_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "jsonb_typeof(provider_raw) = 'object'",
            name="ck_fuel_transactions_provider_raw_object",
        ),
        CheckConstraint(
            "provider_event_type IN "
            "('PURCHASE', 'CREDIT', 'REFUND', 'REVERSAL', 'VOID', 'OTHER', 'UNKNOWN')",
            name="ck_fuel_transactions_provider_event_type",
        ),
        CheckConstraint(
            "transaction_timezone_source IN "
            "('PROVIDER_SUPPLIED', 'PROVIDER_LOCAL_NO_ZONE', 'DATE_ONLY', 'UNKNOWN')",
            name="ck_fuel_transactions_timezone_source",
        ),
        Index("ix_fuel_transactions_tenant_id", "tenant_id"),
        Index("ix_fuel_transactions_tenant_batch", "tenant_id", "batch_id"),
        Index("ix_fuel_transactions_tenant_date", "tenant_id", "transaction_date"),
        Index(
            "ix_fuel_transactions_tenant_provider_txn",
            "tenant_id",
            "source_vendor",
            "account_reference",
            "provider_transaction_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_transaction_identity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_vendor: Mapped[str] = mapped_column(String(40), nullable=False)
    account_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_event_type_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_event_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Provider/source-local calendar date when determinable from the source.
    # Never derived from UTC transaction_datetime (midnight-crossing).
    transaction_datetime_source: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_timezone_source: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transaction_utc_offset: Mapped[str | None] = mapped_column(String(16), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    unit_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_or_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    driver_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merchant_site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    site_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    province_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_code_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_description_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    unit_price_basis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency_raw: Mapped[str | None] = mapped_column(String(16), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    processing_network: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merchant_network: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    provider_discount_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    provider_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    hst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    gst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    pst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    qst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    missed_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    out_of_network_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    pre_tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    billed_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    retail_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    provider_raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # --- TruckERP resolution / derived pricing / posting (NOT provider source truth) ---
    # Parser/source hydration must not populate these. owner_operator_charge_amount is
    # owned by later O/O pricing/settlement logic only.
    truck_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    driver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_operator_payee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    financial_responsibility: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing_agreement_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    settlement_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_operator_charge_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    # Segment 4 O/O pricing provenance (derived; never provider source)
    oo_pricing_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    oo_pricing_rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oo_pricing_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oo_charge_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    oo_benefit_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    oo_pricing_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    oo_pricing_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oo_pricing_inputs_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    downstream_module: Mapped[str | None] = mapped_column(String(40), nullable=True)
    downstream_ack_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    downstream_ack_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gate_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Segment 8 source review (not reconciliation / posting)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    review_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parsed_row_role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="TRANSACTION")
    reviewed_row_role: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FuelOwnerOperatorPricingRule(Base):
    """Effective-dated O/O fuel pricing agreement (Segment 4).

    Belongs to the O/O/payee settlement relationship. Modes:
    NO_DISCOUNT, FULL_PROVIDER_DISCOUNT, FIXED_DISCOUNT, PERCENT_OF_PROVIDER_DISCOUNT.
    percent_of_provider_discount is a fraction in [0, 1] (0.20 = 20% of provider discount).
    """

    __tablename__ = "fuel_oo_pricing_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fuel_oo_pricing_rules_tenant_id_id"),
        CheckConstraint(
            "pricing_mode IN "
            "('NO_DISCOUNT', 'FULL_PROVIDER_DISCOUNT', 'FIXED_DISCOUNT', "
            "'PERCENT_OF_PROVIDER_DISCOUNT')",
            name="ck_fuel_oo_pricing_rules_pricing_mode",
        ),
        CheckConstraint(
            "percent_of_provider_discount IS NULL OR "
            "(percent_of_provider_discount >= 0 AND percent_of_provider_discount <= 1)",
            name="ck_fuel_oo_pricing_rules_percent_range",
        ),
        Index("ix_fuel_oo_pricing_rules_tenant_id", "tenant_id"),
        Index(
            "ix_fuel_oo_pricing_rules_tenant_payee_from",
            "tenant_id",
            "owner_operator_payee_id",
            "effective_from",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_operator_payee_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pricing_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    fixed_discount_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    percent_of_provider_discount: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FuelSourceControl(Base):
    """Provider control / summary evidence (Segment 2).

    Design conceptual split: control rows are not fuel_transactions. Physical
    name: fuel_source_controls. Multiple controls per batch; scope is optional
    and provider-specific (batch/invoice/card/currency/...). Unknown types stay
    UNKNOWN and REVIEW-capable. Parser/source hydration must not also write the
    same source row as a purchase transaction.
    """

    __tablename__ = "fuel_source_controls"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fuel_source_controls_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["fuel_source_batches.tenant_id", "fuel_source_batches.id"],
            name="fk_fuel_source_controls_batch_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "jsonb_typeof(provider_raw) = 'object'",
            name="ck_fuel_source_controls_provider_raw_object",
        ),
        CheckConstraint(
            "control_type IN "
            "('CARD_TOTAL', 'INVOICE_SUMMARY', 'INVOICE_TOTAL', 'STATEMENT_TOTAL', "
            "'CURRENCY_TOTAL', 'UNIT_SUBTOTAL', 'GROUP_SUBTOTAL', 'PRODUCT_SUBTOTAL', "
            "'TAX_CONTROL', 'DISCOUNT_CONTROL', 'PROVIDER_DECLARED_TOTAL', "
            "'CALCULATED_DETAIL_TOTAL', 'VARIANCE', 'OTHER', 'UNKNOWN')",
            name="ck_fuel_source_controls_control_type",
        ),
        CheckConstraint(
            "control_scope IN "
            "('BATCH', 'INVOICE', 'STATEMENT', 'CARD', 'UNIT', 'GROUP', "
            "'PRODUCT', 'CURRENCY', 'TAX', 'OTHER', 'UNKNOWN')",
            name="ck_fuel_source_controls_control_scope",
        ),
        Index("ix_fuel_source_controls_tenant_id", "tenant_id"),
        Index("ix_fuel_source_controls_tenant_batch", "tenant_id", "batch_id"),
        Index("ix_fuel_source_controls_tenant_type", "tenant_id", "control_type"),
        Index("ix_fuel_source_controls_tenant_currency", "tenant_id", "currency"),
        Index(
            "uq_fuel_source_controls_tenant_batch_source_row_order",
            "tenant_id",
            "batch_id",
            "source_row_order",
            unique=True,
            postgresql_where=text("source_row_order IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)

    source_vendor: Mapped[str] = mapped_column(String(40), nullable=False)
    account_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Provider/raw control identity and labels
    provider_control_identity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    control_label_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    control_type_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_type: Mapped[str] = mapped_column(String(40), nullable=False)
    control_scope_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_scope: Mapped[str] = mapped_column(String(20), nullable=False)

    # Optional provider-specific scope keys — not a universal hierarchy
    scope_card_or_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_unit_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_product_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_row_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_row_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    currency_raw: Mapped[str | None] = mapped_column(String(16), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    declared_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    hst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    gst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    pst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    qst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    pre_tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    provider_raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    review_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Segment 8 source review (not reconciliation / posting)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parsed_row_role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="CONTROL")
    reviewed_row_role: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FuelExtractionCorrection(Base):
    """Append-only human extraction correction (Segment 8).

    Never overwrites provider_raw. Human correction is not a provider amendment.
    """

    __tablename__ = "fuel_extraction_corrections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fuel_extraction_corrections_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["fuel_source_batches.tenant_id", "fuel_source_batches.id"],
            name="fk_fuel_extraction_corrections_batch_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "entity_type IN ('TRANSACTION', 'CONTROL')",
            name="ck_fuel_extraction_corrections_entity_type",
        ),
        Index("ix_fuel_extraction_corrections_tenant_id", "tenant_id"),
        Index("ix_fuel_extraction_corrections_tenant_batch", "tenant_id", "batch_id"),
        Index(
            "ix_fuel_extraction_corrections_tenant_entity",
            "tenant_id",
            "entity_type",
            "entity_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parsed_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    reviewed_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(36), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FuelCardAccountAssignment(Base):
    """Effective-dated provider card/account assignment.

    Resolves at transaction datetime. Later moves must not rewrite historical
    truck/driver/payee relationships. Ambiguous/missing -> REVIEW; never
    current-assignment fallback.
    """

    __tablename__ = "fuel_card_account_assignments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "id", name="uq_fuel_card_account_assignments_tenant_id_id"
        ),
        Index("ix_fuel_card_account_assignments_tenant_id", "tenant_id"),
        Index(
            "ix_fuel_card_account_assignments_tenant_card",
            "tenant_id",
            "provider_code",
            "card_or_account_id",
            "effective_from",
        ),
        Index(
            "ix_fuel_card_account_assignments_tenant_account",
            "tenant_id",
            "provider_code",
            "account_reference",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_code: Mapped[str] = mapped_column(String(40), nullable=False)
    account_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    card_or_account_id: Mapped[str] = mapped_column(String(64), nullable=False)

    truck_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    driver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_operator_payee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FuelBvd(Base):
    """BVD source-fidelity rows (Implementation 1). One row per extracted BVD structure."""

    __tablename__ = "fuel_bvd"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_fuel_bvd_tenant_id_id"),
        Index("ix_fuel_bvd_tenant_id", "tenant_id"),
        Index("ix_fuel_bvd_tenant_import", "tenant_id", "import_id"),
        Index("ix_fuel_bvd_tenant_import_row", "tenant_id", "import_id", "source_row_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    import_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    row_type: Mapped[str] = mapped_column(Text, nullable=False)

    invoice_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    hst_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    qst_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    auth_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    driver_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    prov_st: Mapped[str | None] = mapped_column(Text, nullable=True)
    prod: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty: Mapped[str | None] = mapped_column(Text, nullable=True)
    retail: Mapped[str | None] = mapped_column(Text, nullable=True)
    billed: Mapped[str | None] = mapped_column(Text, nullable=True)
    pre_tax_amt: Mapped[str | None] = mapped_column(Text, nullable=True)
    hst: Mapped[str | None] = mapped_column(Text, nullable=True)
    gst: Mapped[str | None] = mapped_column(Text, nullable=True)
    pst: Mapped[str | None] = mapped_column(Text, nullable=True)
    qst: Mapped[str | None] = mapped_column(Text, nullable=True)
    disc_rate: Mapped[str | None] = mapped_column(Text, nullable=True)
    disc_amt: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_amt: Mapped[str | None] = mapped_column(Text, nullable=True)
    cur: Mapped[str | None] = mapped_column(Text, nullable=True)

    row_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    product: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_amount: Mapped[str | None] = mapped_column(Text, nullable=True)
    legend_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    legend_product_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_storage_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_warnings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
