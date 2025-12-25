"""add soft deactivate fields to driver phones

Revision ID: 2f5725edf9c4
Revises: 9d4695445bae
Create Date: 2025-12-25 00:36:57.749531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f5725edf9c4'
down_revision: Union[str, Sequence[str], None] = '9d4695445bae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('driver_phones', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('driver_phones', sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('driver_phones', sa.Column('deactivated_reason', sa.String(length=255), nullable=True))
    # Drop server_default so future inserts rely on app default (optional, keeps DB clean)
    op.alter_column('driver_phones', 'is_active', server_default=None)



def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('driver_phones', 'deactivated_reason')
    op.drop_column('driver_phones', 'deactivated_at')
    op.drop_column('driver_phones', 'is_active')
