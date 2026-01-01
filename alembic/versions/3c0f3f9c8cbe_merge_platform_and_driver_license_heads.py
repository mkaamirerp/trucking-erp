"""Merge platform and driver license heads

Revision ID: 3c0f3f9c8cbe
Revises: 0009_provision_hardening, 2f3c3c4a0b1a
Create Date: 2025-12-31 06:23:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c0f3f9c8cbe"
down_revision: Union[str, Sequence[str], None] = ("0009_provision_hardening", "2f3c3c4a0b1a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
