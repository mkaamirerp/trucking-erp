"""Segment B: charge categories, provider mappings, classification audit.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None

_CATEGORY_SEED = (
    ("FUEL", "Fuel", "Fuel purchases (e.g. diesel/gas)"),
    ("DEF", "DEF", "Diesel exhaust fluid"),
    ("SCALE", "Scale", "Scale/weigh charges"),
    ("LUMPER", "Lumper", "Lumper / unloading labor"),
    ("TOLL", "Toll", "Toll charges"),
    ("CASH_ADVANCE", "Cash advance", "Cash advance"),
    ("PARKING", "Parking", "Parking"),
    ("REPAIR_OR_SERVICE", "Repair or service", "Repair or service"),
    ("PRODUCT_PURCHASE", "Product purchase", "Other product purchase"),
    ("ALLOWANCE", "Allowance", "Allowance"),
    ("LOAD_PAY", "Load pay", "Load pay"),
    ("OTHER", "Other", "Other charge"),
    ("UNMAPPED", "Unmapped", "Not yet classified"),
)


def upgrade() -> None:
    op.create_table(
        "fuel_charge_category",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.UniqueConstraint("code", name="uq_fuel_charge_category_code"),
    )

    category_table = sa.table(
        "fuel_charge_category",
        sa.column("code", sa.String),
        sa.column("display_name", sa.String),
        sa.column("description", sa.Text),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        category_table,
        [
            {
                "code": code,
                "display_name": display_name,
                "description": description,
                "active": True,
            }
            for code, display_name, description in _CATEGORY_SEED
        ],
    )

    op.create_table(
        "fuel_provider_category_mapping",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("provider_code", sa.String(length=40), nullable=False),
        sa.Column("provider_section", sa.String(length=255), nullable=False),
        sa.Column("normalized_reason_key", sa.String(length=255), nullable=False),
        sa.Column("raw_example", sa.String(length=255), nullable=True),
        sa.Column("canonical_category_code", sa.String(length=64), nullable=False),
        sa.Column("mapping_source", sa.String(length=40), nullable=False),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint(
            "mapping_source IN ('PROVIDER_RULE', 'SYSTEM_MAPPING', 'TENANT_MAPPING', 'MANUAL')",
            name="ck_fuel_provider_category_mapping_source",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_category_code"],
            ["fuel_charge_category.code"],
            name="fk_fuel_provider_category_mapping_category",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_fuel_provider_category_mapping_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_fuel_provider_category_mapping_tenant",
        "fuel_provider_category_mapping",
        ["tenant_id"],
    )
    op.create_index(
        "uq_fuel_provider_category_mapping_tenant_scope_key",
        "fuel_provider_category_mapping",
        ["tenant_id", "provider_code", "provider_section", "normalized_reason_key"],
        unique=True,
        postgresql_where=sa.text("active IS TRUE AND tenant_id IS NOT NULL"),
    )

    op.create_table(
        "fuel_transaction_classification_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("fuel_transaction_id", sa.Integer(), nullable=False),
        sa.Column("previous_category", sa.String(length=64), nullable=True),
        sa.Column("proposed_category", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("mapping_id", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("ai_model", sa.String(length=128), nullable=True),
        sa.Column("ai_prompt_version", sa.String(length=64), nullable=True),
        sa.Column("ai_confidence", sa.Numeric(6, 5), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IS NULL OR source IN "
            "('PROVIDER_RULE', 'SYSTEM_MAPPING', 'TENANT_MAPPING', 'MANUAL', 'AI')",
            name="ck_fuel_txn_classification_event_source",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fuel_transaction_id"],
            ["fuel_transactions.tenant_id", "fuel_transactions.id"],
            name="fk_fuel_txn_classification_event_txn",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_id"],
            ["fuel_provider_category_mapping.id"],
            name="fk_fuel_txn_classification_event_mapping",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fuel_txn_classification_event_tenant_txn",
        "fuel_transaction_classification_event",
        ["tenant_id", "fuel_transaction_id"],
    )

    op.add_column(
        "fuel_transactions",
        sa.Column("classification_mapping_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_fuel_transactions_classification_mapping",
        "fuel_transactions",
        "fuel_provider_category_mapping",
        ["classification_mapping_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fuel_transactions_classification_mapping",
        "fuel_transactions",
        type_="foreignkey",
    )
    op.drop_column("fuel_transactions", "classification_mapping_id")
    op.drop_index(
        "ix_fuel_txn_classification_event_tenant_txn",
        table_name="fuel_transaction_classification_event",
    )
    op.drop_table("fuel_transaction_classification_event")
    op.drop_index(
        "uq_fuel_provider_category_mapping_tenant_scope_key",
        table_name="fuel_provider_category_mapping",
    )
    op.drop_index(
        "ix_fuel_provider_category_mapping_tenant",
        table_name="fuel_provider_category_mapping",
    )
    op.drop_table("fuel_provider_category_mapping")
    op.drop_table("fuel_charge_category")
