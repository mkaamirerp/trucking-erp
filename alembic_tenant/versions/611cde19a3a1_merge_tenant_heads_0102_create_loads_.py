"""merge tenant heads 0102_create_loads + b3cfb1d0d9f0

Revision ID: 611cde19a3a1
Revises: 0102_create_loads, b3cfb1d0d9f0
Create Date: 2026-01-23 03:27:13.969018

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = '611cde19a3a1'
down_revision = ('0102_create_loads', 'b3cfb1d0d9f0')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
