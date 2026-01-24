"""Continue platform chain after removing tenant migrations

Revision ID: 3c0f3f9c8cbe
Revises: 0009_provision_hardening
Create Date: 2025-12-31 06:23:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c0f3f9c8cbe"
down_revision: Union[str, Sequence[str], None] = "0009_provision_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
