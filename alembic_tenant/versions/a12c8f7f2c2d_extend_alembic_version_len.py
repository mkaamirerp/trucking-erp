"""Extend alembic_version.version_num length for long revisions.

Revision ID: a12c8f7f2c2d
Revises: b8f9cfe34f1b
Create Date: 2026-01-06 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a12c8f7f2c2d"
down_revision: Union[str, Sequence[str], None] = "b8f9cfe34f1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Increase version_num column to fit long revision IDs."""
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=255),
    )


def downgrade() -> None:
    """Revert version_num length change."""
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=255),
        type_=sa.String(length=32),
    )
