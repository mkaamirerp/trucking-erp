"""Fuel settlement_deduction_candidate column + financial event audit.

Revision ID: b2c3d4e5f6a7
Revises: e3f4a5b6c7d8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fuel_transactions",
        sa.Column("settlement_deduction_candidate", sa.Boolean(), nullable=True),
    )
    op.create_table(
        "fuel_transaction_financial_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("fuel_transaction_id", sa.Integer(), nullable=False),
        sa.Column("previous_financial_responsibility", sa.String(length=64), nullable=True),
        sa.Column("new_financial_responsibility", sa.String(length=64), nullable=True),
        sa.Column("previous_settlement_deduction_candidate", sa.Boolean(), nullable=True),
        sa.Column("new_settlement_deduction_candidate", sa.Boolean(), nullable=True),
        sa.Column("previous_owner_operator_payee_id", sa.Integer(), nullable=True),
        sa.Column("new_owner_operator_payee_id", sa.Integer(), nullable=True),
        sa.Column("previous_driver_id", sa.Integer(), nullable=True),
        sa.Column("new_driver_id", sa.Integer(), nullable=True),
        sa.Column("previous_owner_operator_charge_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("new_owner_operator_charge_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("previous_oo_charge_unit_price", sa.Numeric(14, 6), nullable=True),
        sa.Column("new_oo_charge_unit_price", sa.Numeric(14, 6), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fuel_transaction_id"],
            ["fuel_transactions.tenant_id", "fuel_transactions.id"],
            name="fk_fuel_txn_financial_event_txn",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fuel_txn_financial_event_tenant_txn",
        "fuel_transaction_financial_event",
        ["tenant_id", "fuel_transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fuel_txn_financial_event_tenant_txn",
        table_name="fuel_transaction_financial_event",
    )
    op.drop_table("fuel_transaction_financial_event")
    op.drop_column("fuel_transactions", "settlement_deduction_candidate")
