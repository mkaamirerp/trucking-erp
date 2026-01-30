"""merge tenant heads to single lineage

Revision ID: 8c84780c154b
Revises: 2aa9c2a60b5f, 611cde19a3a1, a91c0b77d3e1, f3a9e1b4c2d7
Create Date: 2026-01-30 07:00:56.270343

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = '8c84780c154b'
down_revision = ('2aa9c2a60b5f', '611cde19a3a1', 'a91c0b77d3e1', 'f3a9e1b4c2d7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
