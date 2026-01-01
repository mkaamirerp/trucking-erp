"""Add global driver license fields

Revision ID: 2f3c3c4a0b1a
Revises: c8a3d0b9c777
Create Date: 2025-12-31 06:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2f3c3c4a0b1a"
down_revision: Union[str, Sequence[str], None] = "c8a3d0b9c777"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drivers", sa.Column("issuing_country", sa.String(length=10), nullable=True))
    op.add_column("drivers", sa.Column("issuing_region", sa.String(length=100), nullable=True))
    op.add_column("drivers", sa.Column("license_number", sa.String(length=100), nullable=True))
    op.add_column("drivers", sa.Column("license_class", sa.String(length=50), nullable=True))
    op.add_column("drivers", sa.Column("license_issue_date", sa.Date(), nullable=True))
    op.add_column("drivers", sa.Column("license_expiry_date", sa.Date(), nullable=True))
    op.create_index("ix_drivers_license_expiry_date", "drivers", ["license_expiry_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_drivers_license_expiry_date", table_name="drivers")
    op.drop_column("drivers", "license_expiry_date")
    op.drop_column("drivers", "license_issue_date")
    op.drop_column("drivers", "license_class")
    op.drop_column("drivers", "license_number")
    op.drop_column("drivers", "issuing_region")
    op.drop_column("drivers", "issuing_country")
