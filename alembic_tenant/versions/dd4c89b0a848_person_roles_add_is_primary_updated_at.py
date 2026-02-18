"""person_roles: add is_primary and updated_at when missing (fix 74ff-created tables).

Revision ID: dd4c89b0a848
Revises: cb313448b94e
Create Date: Tenant schema

74ff8253c43c creates person_roles without is_primary/updated_at; ea59a17db8a3 skips
when table exists. This migration adds the missing columns idempotently.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "dd4c89b0a848"
down_revision = "cb313448b94e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "person_roles" not in inspector.get_table_names(schema="public"):
        return

    cols = {c["name"] for c in inspector.get_columns("person_roles", schema="public")}

    if "is_primary" not in cols:
        op.add_column(
            "person_roles",
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            schema="public",
        )

    if "updated_at" not in cols:
        op.add_column(
            "person_roles",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            schema="public",
        )
        op.execute("UPDATE person_roles SET updated_at = created_at WHERE updated_at IS NULL")
        op.alter_column(
            "person_roles",
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            schema="public",
        )


def downgrade() -> None:
    pass
