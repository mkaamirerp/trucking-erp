"""Fuel Segment 4 O/O pricing rules + transaction provenance columns.

Revision ID: f4e5f6a7b8c9
Revises: f3d4e5f6a7b8

Effective-dated owner-operator fuel pricing agreements. Provider amounts stay
on fuel_transactions; O/O charge/provenance are derived columns only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f4e5f6a7b8c9"
down_revision = "f3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_oo_pricing_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("owner_operator_payee_id", sa.Integer(), nullable=False),
        sa.Column("pricing_mode", sa.String(length=40), nullable=False),
        sa.Column("fixed_discount_per_unit", sa.Numeric(14, 6), nullable=True),
        sa.Column("percent_of_provider_discount", sa.Numeric(10, 6), nullable=True),
        sa.Column("rule_version", sa.String(length=64), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_oo_pricing_rules_tenant_id_id"),
        sa.CheckConstraint(
            "pricing_mode IN "
            "('NO_DISCOUNT', 'FULL_PROVIDER_DISCOUNT', 'FIXED_DISCOUNT', "
            "'PERCENT_OF_PROVIDER_DISCOUNT')",
            name="ck_fuel_oo_pricing_rules_pricing_mode",
        ),
        sa.CheckConstraint(
            "percent_of_provider_discount IS NULL OR "
            "(percent_of_provider_discount >= 0 AND percent_of_provider_discount <= 1)",
            name="ck_fuel_oo_pricing_rules_percent_range",
        ),
    )
    op.create_index(
        "ix_fuel_oo_pricing_rules_tenant_id", "fuel_oo_pricing_rules", ["tenant_id"]
    )
    op.create_index(
        "ix_fuel_oo_pricing_rules_tenant_payee_from",
        "fuel_oo_pricing_rules",
        ["tenant_id", "owner_operator_payee_id", "effective_from"],
    )

    op.add_column(
        "fuel_transactions",
        sa.Column("oo_pricing_mode", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("oo_pricing_rule_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("oo_pricing_rule_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("oo_charge_unit_price", sa.Numeric(14, 6), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("oo_benefit_per_unit", sa.Numeric(14, 6), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("oo_pricing_status", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("oo_pricing_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column(
            "oo_pricing_inputs_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("fuel_transactions", "oo_pricing_inputs_json")
    op.drop_column("fuel_transactions", "oo_pricing_reason")
    op.drop_column("fuel_transactions", "oo_pricing_status")
    op.drop_column("fuel_transactions", "oo_benefit_per_unit")
    op.drop_column("fuel_transactions", "oo_charge_unit_price")
    op.drop_column("fuel_transactions", "oo_pricing_rule_version")
    op.drop_column("fuel_transactions", "oo_pricing_rule_id")
    op.drop_column("fuel_transactions", "oo_pricing_mode")
    op.drop_index(
        "ix_fuel_oo_pricing_rules_tenant_payee_from", table_name="fuel_oo_pricing_rules"
    )
    op.drop_index("ix_fuel_oo_pricing_rules_tenant_id", table_name="fuel_oo_pricing_rules")
    op.drop_table("fuel_oo_pricing_rules")
