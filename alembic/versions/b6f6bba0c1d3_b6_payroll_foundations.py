"""B6: Payroll foundations (manual inputs)

Revision ID: b6f6bba0c1d3
Revises: 5b013e5ac73d
Create Date: 2025-12-31 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6f6bba0c1d3'
down_revision: Union[str, Sequence[str], None] = '5b013e5ac73d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pay_periods",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pay_periods_tenant_id", "pay_periods", ["tenant_id"])
    op.create_index("ix_pay_periods_status", "pay_periods", ["status"])
    op.create_index("ix_pay_periods_dates", "pay_periods", ["tenant_id", "start_date", "end_date"])

    op.create_table(
        "pay_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("drivers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pay_type", sa.String(length=20), nullable=False),
        sa.Column("rate_amount", sa.Numeric(12, 4), nullable=True),
        sa.Column("rate_unit", sa.String(length=30), nullable=True),
        sa.Column("percentage_basis_points", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("effective_start", sa.Date(), nullable=False, server_default=sa.text("current_date")),
        sa.Column("effective_end", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pay_profiles_tenant_driver", "pay_profiles", ["tenant_id", "driver_id"])
    op.create_index("ix_pay_profiles_active", "pay_profiles", ["tenant_id", "is_active"])

    op.create_table(
        "pay_entries",
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
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("drivers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pay_profile_id",
            sa.Integer(),
            sa.ForeignKey("pay_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=True),
        sa.Column("rate_amount", sa.Numeric(12, 4), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pay_entries_tenant_period", "pay_entries", ["tenant_id", "pay_period_id"])
    op.create_index("ix_pay_entries_tenant_driver", "pay_entries", ["tenant_id", "driver_id"])
    op.create_index("ix_pay_entries_tenant_entry_type", "pay_entries", ["tenant_id", "entry_type"])
    op.create_index("ix_pay_entries_active", "pay_entries", ["tenant_id", "is_active"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pay_entries_active", table_name="pay_entries")
    op.drop_index("ix_pay_entries_tenant_entry_type", table_name="pay_entries")
    op.drop_index("ix_pay_entries_tenant_driver", table_name="pay_entries")
    op.drop_index("ix_pay_entries_tenant_period", table_name="pay_entries")
    op.drop_table("pay_entries")

    op.drop_index("ix_pay_profiles_active", table_name="pay_profiles")
    op.drop_index("ix_pay_profiles_tenant_driver", table_name="pay_profiles")
    op.drop_table("pay_profiles")

    op.drop_index("ix_pay_periods_dates", table_name="pay_periods")
    op.drop_index("ix_pay_periods_status", table_name="pay_periods")
    op.drop_index("ix_pay_periods_tenant_id", table_name="pay_periods")
    op.drop_table("pay_periods")
