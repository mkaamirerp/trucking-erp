"""Add driver document subtype and issuing_country snapshot

Revision ID: 4b5c1a9c1d5f
Revises: 3c0f3f9c8cbe
Create Date: 2025-12-31 06:28:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4b5c1a9c1d5f"
down_revision: Union[str, Sequence[str], None] = "3c0f3f9c8cbe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("driver_documents", sa.Column("doc_subtype", sa.String(length=50), nullable=True))
    op.add_column("driver_documents", sa.Column("issuing_country_snapshot", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("driver_documents", "issuing_country_snapshot")
    op.drop_column("driver_documents", "doc_subtype")
