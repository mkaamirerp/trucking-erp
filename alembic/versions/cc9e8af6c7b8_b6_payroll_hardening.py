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
    # Pay periods: close metadata
    op.add_column("pay_periods", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))

    # Pay entries: work_date, reference_code, created_by/updated_by
    op.add_column("pay_entries", sa.Column("work_date", sa.Date(), nullable=False, server_default=sa.text("current_date")))
    op.add_column("pay_entries", sa.Column("reference_code", sa.String(length=100), nullable=False, server_default=""))
    op.add_column("pay_entries", sa.Column("created_by", sa.String(length=100), nullable=True))
    op.add_column("pay_entries", sa.Column("updated_by", sa.String(length=100), nullable=True))

    # Unique constraint to prevent duplicates
    op.create_index(
        "uq_pay_entries_unique",
        "pay_entries",
        ["tenant_id", "driver_id", "entry_type", "work_date", "reference_code"],
        unique=True,
    )

    # Drop server defaults now that column is populated
    op.alter_column("pay_entries", "work_date", server_default=None)
    op.alter_column("pay_entries", "reference_code", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_pay_entries_unique", table_name="pay_entries")
    op.drop_column("pay_entries", "updated_by")
    op.drop_column("pay_entries", "created_by")
    op.drop_column("pay_entries", "reference_code")
    op.drop_column("pay_entries", "work_date")
    op.drop_column("pay_periods", "closed_at")
