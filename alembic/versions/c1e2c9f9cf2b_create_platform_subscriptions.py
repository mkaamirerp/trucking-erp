"""Create platform_subscriptions table for signup flow

Revision ID: c1e2c9f9cf2b
Revises: c1e2c9f9cf2a
Create Date: 2026-01-11 07:22:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1e2c9f9cf2b"
down_revision: Union[str, Sequence[str], None] = "c1e2c9f9cf2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "platform_subscriptions" not in tables:
        op.create_table(
            "platform_subscriptions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id",
                sa.BigInteger,
                sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("plan", sa.String(50), nullable=False, server_default="TRIAL"),
            sa.Column("status", sa.String(50), nullable=False, server_default="TRIAL_ACTIVE"),
            sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "platform_subscriptions" in tables:
        op.drop_table("platform_subscriptions")
