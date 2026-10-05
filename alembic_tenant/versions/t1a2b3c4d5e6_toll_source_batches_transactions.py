"""Toll source batches and canonical transactions (Segment 1).

Revision ID: t1a2b3c4d5e6
Revises: m7n8o9p0q1r2

Tenant data-plane only. Canonical Toll tables stay small and vehicle/unit-based.
Provider transaction identity is not the primary key. Date+unit is not unique.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "t1a2b3c4d5e6"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "toll_source_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=True),
        sa.Column("provider_code", sa.String(length=40), nullable=True),
        sa.Column("provider_connection_id", sa.Integer(), nullable=True),
        sa.Column("account_reference", sa.String(length=128), nullable=True),
        sa.Column("source_storage_ref", sa.String(length=512), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column("source_import_ref", sa.String(length=128), nullable=True),
        sa.Column("statement_start", sa.Date(), nullable=True),
        sa.Column("statement_end", sa.Date(), nullable=True),
        sa.Column("invoice_number", sa.String(length=128), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="RECEIVED", nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_toll_source_batches_tenant_id_id"),
        sa.CheckConstraint(
            "source_type IN ('API', 'FILE', 'MANUAL')",
            name="ck_toll_source_batches_source_type",
        ),
        sa.CheckConstraint(
            "file_format IS NULL OR file_format IN ('PDF', 'CSV')",
            name="ck_toll_source_batches_file_format",
        ),
        sa.CheckConstraint(
            "source_type = 'FILE' OR file_format IS NULL",
            name="ck_toll_source_batches_file_format_file_only",
        ),
    )
    op.create_index("ix_toll_source_batches_tenant_id", "toll_source_batches", ["tenant_id"])
    op.create_index(
        "ix_toll_source_batches_tenant_provider",
        "toll_source_batches",
        ["tenant_id", "provider_code"],
    )
    op.create_index(
        "ix_toll_source_batches_tenant_status",
        "toll_source_batches",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_toll_source_batches_tenant_source_hash",
        "toll_source_batches",
        ["tenant_id", "source_hash"],
    )
    op.create_index(
        "ix_toll_source_batches_tenant_source_import_ref",
        "toll_source_batches",
        ["tenant_id", "source_import_ref"],
    )

    op.create_table(
        "toll_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=128), nullable=True),
        sa.Column("source_row_order", sa.Integer(), nullable=False),
        sa.Column("source_row_id", sa.String(length=128), nullable=True),
        sa.Column("transaction_datetime_source", sa.Text(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("transaction_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("truck_id", sa.Integer(), nullable=True),
        sa.Column("unit_number_snapshot", sa.String(length=64), nullable=True),
        sa.Column("toll_agency_code", sa.String(length=32), nullable=True),
        sa.Column("toll_agency_name", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("read_type", sa.String(length=16), nullable=True),
        sa.Column("device_number", sa.String(length=64), nullable=True),
        sa.Column("plate_number", sa.String(length=32), nullable=True),
        sa.Column("plate_state", sa.String(length=16), nullable=True),
        sa.Column("dispute_status", sa.String(length=64), nullable=True),
        sa.Column(
            "provider_raw",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_toll_transactions_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "source_row_order",
            name="uq_toll_transactions_tenant_batch_source_row_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["toll_source_batches.tenant_id", "toll_source_batches.id"],
            name="fk_toll_transactions_batch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_toll_transactions_truck_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provider_raw) = 'object'",
            name="ck_toll_transactions_provider_raw_object",
        ),
        sa.CheckConstraint(
            "transaction_type IN ('NORMAL', 'VIOLATION')",
            name="ck_toll_transactions_transaction_type",
        ),
        sa.CheckConstraint(
            "read_type IS NULL OR read_type IN ('DEVICE', 'PLATE')",
            name="ck_toll_transactions_read_type",
        ),
    )
    op.create_index("ix_toll_transactions_tenant_id", "toll_transactions", ["tenant_id"])
    op.create_index(
        "ix_toll_transactions_tenant_batch",
        "toll_transactions",
        ["tenant_id", "batch_id"],
    )
    op.create_index(
        "ix_toll_transactions_tenant_date",
        "toll_transactions",
        ["tenant_id", "transaction_date"],
    )
    op.create_index(
        "ix_toll_transactions_tenant_truck_datetime",
        "toll_transactions",
        ["tenant_id", "truck_id", "transaction_datetime"],
    )
    op.create_index(
        "ix_toll_transactions_tenant_unit_datetime",
        "toll_transactions",
        ["tenant_id", "unit_number_snapshot", "transaction_datetime"],
    )
    op.create_index(
        "ix_toll_transactions_tenant_provider_txn",
        "toll_transactions",
        ["tenant_id", "provider_transaction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_toll_transactions_tenant_provider_txn", table_name="toll_transactions")
    op.drop_index("ix_toll_transactions_tenant_unit_datetime", table_name="toll_transactions")
    op.drop_index("ix_toll_transactions_tenant_truck_datetime", table_name="toll_transactions")
    op.drop_index("ix_toll_transactions_tenant_date", table_name="toll_transactions")
    op.drop_index("ix_toll_transactions_tenant_batch", table_name="toll_transactions")
    op.drop_index("ix_toll_transactions_tenant_id", table_name="toll_transactions")
    op.drop_table("toll_transactions")
    op.drop_index("ix_toll_source_batches_tenant_source_import_ref", table_name="toll_source_batches")
    op.drop_index("ix_toll_source_batches_tenant_source_hash", table_name="toll_source_batches")
    op.drop_index("ix_toll_source_batches_tenant_status", table_name="toll_source_batches")
    op.drop_index("ix_toll_source_batches_tenant_provider", table_name="toll_source_batches")
    op.drop_index("ix_toll_source_batches_tenant_id", table_name="toll_source_batches")
    op.drop_table("toll_source_batches")
