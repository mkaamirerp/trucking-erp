"""Phase 9.7: driver documents soft deactivate

Revision ID: 5b013e5ac73d
Revises: 2f5725edf9c4
Create Date: 2025-12-25 02:29:50.207828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b013e5ac73d'
down_revision: Union[str, Sequence[str], None] = '2f5725edf9c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "driver_documents",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "driver_documents",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "driver_documents",
        sa.Column("deactivated_reason", sa.String(length=255), nullable=True),
    )

    op.create_index("ix_driver_documents_is_active", "driver_documents", ["is_active"])

    # remove server_default after backfill safety
    op.alter_column("driver_documents", "is_active", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_driver_documents_is_active", table_name="driver_documents")
    op.drop_column("driver_documents", "deactivated_reason")
    op.drop_column("driver_documents", "deactivated_at")
    op.drop_column("driver_documents", "is_active")

