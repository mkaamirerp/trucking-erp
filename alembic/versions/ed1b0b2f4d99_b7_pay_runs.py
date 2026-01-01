"""B7 pay runs and items

Revision ID: ed1b0b2f4d99
Revises: cc9e8af6c7b8
Create Date: 2026-01-01 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'ed1b0b2f4d99'
down_revision: Union[str, Sequence[str], None] = 'cc9e8af6c7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pay_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pay_period_id",
            sa.Integer(),
            sa.ForeignKey("pay_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("totals_snapshot", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_pay_runs_unique_period", "pay_runs", ["tenant_id", "pay_period_id"], unique=True)
    op.create_index("ix_pay_runs_status", "pay_runs", ["tenant_id", "status"])

    op.create_table(
        "pay_run_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "pay_run_id",
            sa.Integer(),
            sa.ForeignKey("pay_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("drivers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "source_entry_id",
            sa.Integer(),
            sa.ForeignKey("pay_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_pay_run_items_pay_run", "pay_run_items", ["pay_run_id"])
    op.create_index("ix_pay_run_items_driver", "pay_run_items", ["pay_run_id", "driver_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pay_run_items_driver", table_name="pay_run_items")
    op.drop_index("ix_pay_run_items_pay_run", table_name="pay_run_items")
    op.drop_table("pay_run_items")

    op.drop_index("ix_pay_runs_status", table_name="pay_runs")
    op.drop_index("ix_pay_runs_unique_period", table_name="pay_runs")
    op.drop_table("pay_runs")
