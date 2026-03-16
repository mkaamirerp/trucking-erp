"""Add review/audit fields to person_applications.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-11

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "person_applications" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("person_applications")}
    additions = [
        ("reviewed_at", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)),
        ("reviewed_by_user_id", sa.Column("reviewed_by_user_id", sa.BigInteger(), nullable=True)),
        ("approved_at", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)),
        ("approved_by_user_id", sa.Column("approved_by_user_id", sa.BigInteger(), nullable=True)),
        ("rejection_reason", sa.Column("rejection_reason", sa.Text(), nullable=True)),
    ]
    for name, column in additions:
        if name not in cols:
            op.add_column("person_applications", column, schema="public")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "person_applications" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("person_applications")}
    for name in [
        "rejection_reason",
        "approved_by_user_id",
        "approved_at",
        "reviewed_by_user_id",
        "reviewed_at",
    ]:
        if name in cols:
            op.drop_column("person_applications", name, schema="public")
