"""tenant_users: add theme preference column.

Revision ID: t2u3v4w5x6y7
Revises: s1b2c3d4e5f6
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t2u3v4w5x6y7"
down_revision = "s1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_users",
        sa.Column(
            "theme",
            sa.String(20),
            nullable=False,
            server_default="dark",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_users", "theme")
