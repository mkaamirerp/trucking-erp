"""Drop tenant DB tenants table (Lane C)

Revision ID: h3c4d5e6f7a8
Revises: g2b3c4d5e6f7
Create Date: 2026-03-15

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "h3c4d5e6f7a8"
down_revision = "g2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS tenants CASCADE"))


def downgrade() -> None:
    pass
