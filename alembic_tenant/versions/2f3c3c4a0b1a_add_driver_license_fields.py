"""Add global driver license fields

Revision ID: 2f3c3c4a0b1a
Revises: tc8a3d0b9c777
Create Date: 2025-12-31 06:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2f3c3c4a0b1a"
down_revision: Union[str, Sequence[str], None] = "tc8a3d0b9c777"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {col["name"] for col in inspector.get_columns("drivers", schema="public")}

    add_cols = [
        ("issuing_country", sa.String(length=10)),
        ("issuing_region", sa.String(length=100)),
        ("license_number", sa.String(length=100)),
        ("license_class", sa.String(length=50)),
        ("license_issue_date", sa.Date()),
        ("license_expiry_date", sa.Date()),
    ]

    for name, coltype in add_cols:
        if name not in existing_columns:
            op.add_column("drivers", sa.Column(name, coltype, nullable=True))

    indexes = {idx["name"] for idx in inspector.get_indexes("drivers", schema="public")}
    if "ix_drivers_license_expiry_date" not in indexes:
        op.create_index("ix_drivers_license_expiry_date", "drivers", ["license_expiry_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_drivers_license_expiry_date", table_name="drivers")
    op.drop_column("drivers", "license_expiry_date")
    op.drop_column("drivers", "license_issue_date")
    op.drop_column("drivers", "license_class")
    op.drop_column("drivers", "license_number")
    op.drop_column("drivers", "issuing_region")
    op.drop_column("drivers", "issuing_country")
