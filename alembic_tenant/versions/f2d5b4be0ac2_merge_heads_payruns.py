"""Merge heads: employee roles + pay runs

Revision ID: f2d5b4be0ac2
Revises: 7f8e2b1e7e7f, ed1b0b2f4d99
Create Date: 2026-01-01 02:20:00.000000

"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = 'f2d5b4be0ac2'
down_revision: Union[str, Sequence[str], None] = ('7f8e2b1e7e7f', 'ed1b0b2f4d99')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration; no-op."""
    pass


def downgrade() -> None:
    """Merge migration; no-op."""
    pass
