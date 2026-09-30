"""Fuel settlement_deduction_basis_amount + financial event audit columns.

Revision ID: c5d6e7f8a9b0
Revises: b2c3d4e5f6a7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fuel_transactions",
        sa.Column("settlement_deduction_basis_amount", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "fuel_transaction_financial_event",
        sa.Column("previous_settlement_deduction_basis_amount", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "fuel_transaction_financial_event",
        sa.Column("new_settlement_deduction_basis_amount", sa.Numeric(14, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fuel_transaction_financial_event", "new_settlement_deduction_basis_amount")
    op.drop_column("fuel_transaction_financial_event", "previous_settlement_deduction_basis_amount")
    op.drop_column("fuel_transactions", "settlement_deduction_basis_amount")
