"""merge tenant heads

Revision ID: 168cb4699baf
Revises: 9e4f2c1b7a6d, a867a473deb7
Create Date: 2026-02-02 05:38:53.978960

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = '168cb4699baf'
down_revision = ('9e4f2c1b7a6d', 'a867a473deb7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
