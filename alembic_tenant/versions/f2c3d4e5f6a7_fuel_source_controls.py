"""Fuel source control totals (Segment 2).

Revision ID: f2c3d4e5f6a7
Revises: f1b2c3d4e5f6

Tenant data-plane only. Provider controls are reconciliation evidence, never
purchase rows. Decimal/NUMERIC scales follow Module Design §1.5.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2c3d4e5f6a7"
down_revision = "f1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_source_controls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("source_vendor", sa.String(length=40), nullable=False),
        sa.Column("account_reference", sa.String(length=128), nullable=True),
        sa.Column("provider_control_identity", sa.String(length=128), nullable=True),
        sa.Column("control_label_raw", sa.String(length=255), nullable=True),
        sa.Column("control_type_raw", sa.String(length=64), nullable=True),
        sa.Column("control_type", sa.String(length=40), nullable=False),
        sa.Column("control_scope_raw", sa.String(length=64), nullable=True),
        sa.Column("control_scope", sa.String(length=20), nullable=False),
        sa.Column("scope_card_or_account_id", sa.String(length=64), nullable=True),
        sa.Column("scope_unit_number_snapshot", sa.String(length=64), nullable=True),
        sa.Column("scope_product_raw", sa.String(length=64), nullable=True),
        sa.Column("invoice_number", sa.String(length=128), nullable=True),
        sa.Column("source_row_order", sa.Integer(), nullable=True),
        sa.Column("source_row_id", sa.String(length=128), nullable=True),
        sa.Column("currency_raw", sa.String(length=16), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=True),
        sa.Column("declared_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("hst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("gst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("pst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("qst_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("pre_tax_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column(
            "provider_raw",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("requires_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("review_reason", sa.String(length=64), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_source_controls_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["fuel_source_batches.tenant_id", "fuel_source_batches.id"],
            name="fk_fuel_source_controls_batch_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provider_raw) = 'object'",
            name="ck_fuel_source_controls_provider_raw_object",
        ),
        sa.CheckConstraint(
            "control_type IN "
            "('CARD_TOTAL', 'INVOICE_SUMMARY', 'INVOICE_TOTAL', 'STATEMENT_TOTAL', "
            "'CURRENCY_TOTAL', 'UNIT_SUBTOTAL', 'GROUP_SUBTOTAL', 'PRODUCT_SUBTOTAL', "
            "'TAX_CONTROL', 'DISCOUNT_CONTROL', 'PROVIDER_DECLARED_TOTAL', "
            "'CALCULATED_DETAIL_TOTAL', 'VARIANCE', 'OTHER', 'UNKNOWN')",
            name="ck_fuel_source_controls_control_type",
        ),
        sa.CheckConstraint(
            "control_scope IN "
            "('BATCH', 'INVOICE', 'STATEMENT', 'CARD', 'UNIT', 'GROUP', "
            "'PRODUCT', 'CURRENCY', 'TAX', 'OTHER', 'UNKNOWN')",
            name="ck_fuel_source_controls_control_scope",
        ),
    )
    op.create_index("ix_fuel_source_controls_tenant_id", "fuel_source_controls", ["tenant_id"])
    op.create_index(
        "ix_fuel_source_controls_tenant_batch",
        "fuel_source_controls",
        ["tenant_id", "batch_id"],
    )
    op.create_index(
        "ix_fuel_source_controls_tenant_type",
        "fuel_source_controls",
        ["tenant_id", "control_type"],
    )
    op.create_index(
        "ix_fuel_source_controls_tenant_currency",
        "fuel_source_controls",
        ["tenant_id", "currency"],
    )
    op.create_index(
        "uq_fuel_source_controls_tenant_batch_source_row_order",
        "fuel_source_controls",
        ["tenant_id", "batch_id", "source_row_order"],
        unique=True,
        postgresql_where=sa.text("source_row_order IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_fuel_source_controls_tenant_batch_source_row_order",
        table_name="fuel_source_controls",
    )
    op.drop_index("ix_fuel_source_controls_tenant_currency", table_name="fuel_source_controls")
    op.drop_index("ix_fuel_source_controls_tenant_type", table_name="fuel_source_controls")
    op.drop_index("ix_fuel_source_controls_tenant_batch", table_name="fuel_source_controls")
    op.drop_index("ix_fuel_source_controls_tenant_id", table_name="fuel_source_controls")
    op.drop_table("fuel_source_controls")
