"""driver_profiles: add is_active when missing (74ff creates table without it).

Revision ID: e8f9a0b1c2d3
Revises: dd4c89b0a848
Create Date: Tenant schema

Idempotent: adds is_active only if missing.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e8f9a0b1c2d3"
down_revision = "dd4c89b0a848"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "driver_profiles" not in inspector.get_table_names(schema="public"):
        return
    cols = {c["name"] for c in inspector.get_columns("driver_profiles", schema="public")}
    if "is_active" not in cols:
        op.add_column(
            "driver_profiles",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            schema="public",
        )


def downgrade() -> None:
    pass
