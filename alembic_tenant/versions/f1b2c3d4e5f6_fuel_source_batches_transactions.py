"""Fuel source batches and canonical transactions (Segment 1).

Revision ID: f1b2c3d4e5f6
Revises: f0a1c2d3e4f5

Tenant data-plane only. Decimal/NUMERIC scales follow Module Design §1.5.
Provider transaction identity is not the primary key.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1b2c3d4e5f6"
down_revision = "f0a1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_source_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider_code", sa.String(length=40), nullable=False),
        sa.Column("provider_connection_id", sa.Integer(), nullable=True),
        sa.Column("account_reference", sa.String(length=128), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("invoice_number", sa.String(length=128), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("statement_start", sa.Date(), nullable=True),
        sa.Column("statement_end", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("source_storage_ref", sa.String(length=512), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("remote_filename", sa.String(length=512), nullable=True),
        sa.Column("remote_timestamp", sa.String(length=128), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("parser_rule_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="UPLOADED", nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by", sa.String(length=36), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_source_batches_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "provider_connection_id"],
            ["fuel_provider_connections.tenant_id", "fuel_provider_connections.id"],
            name="fk_fuel_source_batches_provider_connection_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "source_type IN ('PDF', 'STRUCTURED_FILE', 'SFTP_FILE', 'MANUAL_DRIVER', 'API')",
            name="ck_fuel_source_batches_source_type",
        ),
    )
    op.create_index("ix_fuel_source_batches_tenant_id", "fuel_source_batches", ["tenant_id"])
    op.create_index(
        "ix_fuel_source_batches_tenant_provider",
        "fuel_source_batches",
        ["tenant_id", "provider_code"],
    )
    op.create_index(
        "ix_fuel_source_batches_tenant_source_hash",
        "fuel_source_batches",
        ["tenant_id", "source_hash"],
        unique=True,
        postgresql_where=sa.text("source_hash IS NOT NULL"),
    )

    op.create_table(
        "fuel_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("provider_transaction_identity", sa.String(length=128), nullable=True),
        sa.Column("source_row_order", sa.Integer(), nullable=False),
        sa.Column("source_row_id", sa.String(length=128), nullable=True),
        sa.Column("source_vendor", sa.String(length=40), nullable=False),
        sa.Column("account_reference", sa.String(length=128), nullable=True),
        # provider_event_type_raw = exact provider terminology; canonical is TruckERP class.
        sa.Column("provider_event_type_raw", sa.String(length=64), nullable=True),
        sa.Column("provider_event_type", sa.String(length=20), nullable=False),
        sa.Column("transaction_datetime_source", sa.Text(), nullable=False),
        sa.Column("transaction_timezone_source", sa.String(length=40), nullable=False),
        sa.Column("transaction_timezone", sa.String(length=64), nullable=True),
        sa.Column("transaction_utc_offset", sa.String(length=16), nullable=True),
        # Provider/source-local calendar date; never derived from UTC transaction_datetime.
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("transaction_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unit_number_snapshot", sa.String(length=64), nullable=True),
        sa.Column("card_or_account_id", sa.String(length=64), nullable=True),
        sa.Column("driver_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("merchant_site", sa.String(length=255), nullable=True),
        sa.Column("site_number", sa.String(length=64), nullable=True),
        sa.Column("site_name", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("province_state", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("product", sa.String(length=64), nullable=True),
        sa.Column("product_code_raw", sa.String(length=64), nullable=True),
        sa.Column("product_description_raw", sa.String(length=255), nullable=True),
        sa.Column("quantity_unit", sa.String(length=16), nullable=True),
        sa.Column("unit_price_basis", sa.String(length=40), nullable=True),
        # currency_raw = exact provider representation (e.g. BVD CN); currency = ISO (CAD).
        sa.Column("currency_raw", sa.String(length=16), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("processing_network", sa.String(length=64), nullable=True),
        sa.Column("merchant_network", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(14, 6), nullable=True),
        sa.Column("provider_discount_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("provider_discount_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("hst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("gst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("pst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("qst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("missed_discount_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("out_of_network_fee", sa.Numeric(14, 4), nullable=True),
        sa.Column("pre_tax_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("billed_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("retail_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column(
            "provider_raw",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        # Derived pricing / resolution placeholders — not provider source truth.
        # Segment 1 and provider parsing must not populate owner_operator_charge_amount.
        sa.Column("truck_id", sa.Integer(), nullable=True),
        sa.Column("driver_id", sa.Integer(), nullable=True),
        sa.Column("owner_operator_payee_id", sa.Integer(), nullable=True),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("financial_responsibility", sa.String(length=64), nullable=True),
        sa.Column("pricing_agreement_ref", sa.String(length=64), nullable=True),
        sa.Column("settlement_ref", sa.String(length=64), nullable=True),
        sa.Column("owner_operator_charge_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("downstream_module", sa.String(length=40), nullable=True),
        sa.Column("downstream_ack_status", sa.String(length=40), nullable=True),
        sa.Column("downstream_ack_ref", sa.String(length=128), nullable=True),
        sa.Column("gate_status", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_transactions_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "source_row_order",
            name="uq_fuel_transactions_tenant_batch_source_row_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["fuel_source_batches.tenant_id", "fuel_source_batches.id"],
            name="fk_fuel_transactions_batch_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provider_raw) = 'object'",
            name="ck_fuel_transactions_provider_raw_object",
        ),
        sa.CheckConstraint(
            "provider_event_type IN "
            "('PURCHASE', 'CREDIT', 'REFUND', 'REVERSAL', 'VOID', 'OTHER', 'UNKNOWN')",
            name="ck_fuel_transactions_provider_event_type",
        ),
        sa.CheckConstraint(
            "transaction_timezone_source IN "
            "('PROVIDER_SUPPLIED', 'PROVIDER_LOCAL_NO_ZONE', 'DATE_ONLY', 'UNKNOWN')",
            name="ck_fuel_transactions_timezone_source",
        ),
    )
    op.create_index("ix_fuel_transactions_tenant_id", "fuel_transactions", ["tenant_id"])
    op.create_index(
        "ix_fuel_transactions_tenant_batch",
        "fuel_transactions",
        ["tenant_id", "batch_id"],
    )
    op.create_index(
        "ix_fuel_transactions_tenant_date",
        "fuel_transactions",
        ["tenant_id", "transaction_date"],
    )
    op.create_index(
        "ix_fuel_transactions_tenant_provider_txn",
        "fuel_transactions",
        ["tenant_id", "source_vendor", "account_reference", "provider_transaction_identity"],
    )


def downgrade() -> None:
    op.drop_index("ix_fuel_transactions_tenant_provider_txn", table_name="fuel_transactions")
    op.drop_index("ix_fuel_transactions_tenant_date", table_name="fuel_transactions")
    op.drop_index("ix_fuel_transactions_tenant_batch", table_name="fuel_transactions")
    op.drop_index("ix_fuel_transactions_tenant_id", table_name="fuel_transactions")
    op.drop_table("fuel_transactions")
    op.drop_index("ix_fuel_source_batches_tenant_source_hash", table_name="fuel_source_batches")
    op.drop_index("ix_fuel_source_batches_tenant_provider", table_name="fuel_source_batches")
    op.drop_index("ix_fuel_source_batches_tenant_id", table_name="fuel_source_batches")
    op.drop_table("fuel_source_batches")
