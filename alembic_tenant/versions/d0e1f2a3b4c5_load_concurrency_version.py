"""Add loads.concurrency_version for optimistic concurrency (CAS writes).

Revision ID: d0e1f2a3b4c5
Revises: c7d6e5f4a3b2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c7d6e5f4a3b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "loads",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("loads", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_column("loads", "concurrency_version")
