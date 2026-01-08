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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns("alembic_version")
    version_col = next((col for col in columns if col["name"] == "version_num"), None)
    if not version_col:
        return

    existing_type = version_col["type"]
    existing_length = getattr(existing_type, "length", None)
    if isinstance(existing_type, sa.String) and (existing_length is None or existing_length < 255):
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=existing_type,
            type_=sa.String(length=255),
        )


def downgrade() -> None:
    """Revert version_num length change."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns("alembic_version")
    version_col = next((col for col in columns if col["name"] == "version_num"), None)
    if not version_col:
        return

    existing_type = version_col["type"]
    existing_length = getattr(existing_type, "length", None)
    if isinstance(existing_type, sa.String) and (existing_length is None or existing_length > 32):
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=existing_type,
            type_=sa.String(length=32),
        )
