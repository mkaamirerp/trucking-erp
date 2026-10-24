"""Shared DDL for ln01_load_number_periods paired revisions (Task 14 checkpoint 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def upgrade_tenant_load_number_periods() -> None:
    op.create_table(
        "tenant_load_number_periods",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("next_numeric", sa.BigInteger(), server_default="1", nullable=False),
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
        sa.PrimaryKeyConstraint("tenant_id", "period", name="pk_tenant_load_number_periods"),
        sa.CheckConstraint(
            "period ~ '^[0-9]{4}-[0-9]{2}$'",
            name="ck_tenant_load_number_periods_period",
        ),
    )


def downgrade_tenant_load_number_periods() -> None:
    op.drop_table("tenant_load_number_periods")
