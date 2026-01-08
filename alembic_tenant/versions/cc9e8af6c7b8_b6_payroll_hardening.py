"""B6 payroll hardening: immutability, boundaries, uniqueness

Revision ID: cc9e8af6c7b8
Revises: b6f6bba0c1d3
Create Date: 2026-01-01 01:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc9e8af6c7b8'
down_revision: Union[str, Sequence[str], None] = 'b6f6bba0c1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Pay periods: close metadata
    pay_period_cols = {col["name"] for col in inspector.get_columns("pay_periods")} if inspector.has_table("pay_periods") else set()
    if "closed_at" not in pay_period_cols:
        op.add_column("pay_periods", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))

    # Pay entries: work_date, reference_code, created_by/updated_by
    pay_entry_cols = {col["name"] for col in inspector.get_columns("pay_entries")} if inspector.has_table("pay_entries") else set()
    if "work_date" not in pay_entry_cols:
        op.add_column("pay_entries", sa.Column("work_date", sa.Date(), nullable=False, server_default=sa.text("current_date")))
    if "reference_code" not in pay_entry_cols:
        op.add_column("pay_entries", sa.Column("reference_code", sa.String(length=100), nullable=False, server_default=""))
    if "created_by" not in pay_entry_cols:
        op.add_column("pay_entries", sa.Column("created_by", sa.String(length=100), nullable=True))
    if "updated_by" not in pay_entry_cols:
        op.add_column("pay_entries", sa.Column("updated_by", sa.String(length=100), nullable=True))

    pay_entry_indexes = {idx["name"] for idx in inspector.get_indexes("pay_entries")} if inspector.has_table("pay_entries") else set()
    if "uq_pay_entries_unique" not in pay_entry_indexes:
        op.create_index(
            "uq_pay_entries_unique",
            "pay_entries",
            ["tenant_id", "driver_id", "entry_type", "work_date", "reference_code"],
            unique=True,
        )

    # Drop server defaults now that column is populated
    if inspector.has_table("pay_entries") and "work_date" in pay_entry_cols:
        op.alter_column("pay_entries", "work_date", server_default=None)
    if inspector.has_table("pay_entries") and "reference_code" in pay_entry_cols:
        op.alter_column("pay_entries", "reference_code", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_pay_entries_unique", table_name="pay_entries")
    op.drop_column("pay_entries", "updated_by")
    op.drop_column("pay_entries", "created_by")
    op.drop_column("pay_entries", "reference_code")
    op.drop_column("pay_entries", "work_date")
    op.drop_column("pay_periods", "closed_at")
