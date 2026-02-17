"""people: add is_active (required by app provisioning)

Revision ID: cb313448b94e
Revises: a5b6c7d8e9f0
Create Date: Tenant schema only

"""
from alembic import op
import sqlalchemy as sa

revision = "cb313448b94e"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column (nullable first so it won't fail on existing rows)
    op.add_column("people", sa.Column("is_active", sa.Boolean(), nullable=True))

    # Backfill existing rows
    op.execute("UPDATE people SET is_active = TRUE WHERE is_active IS NULL")

    # Enforce NOT NULL + default TRUE for future inserts
    op.alter_column("people", "is_active", nullable=False, server_default=sa.text("TRUE"))


def downgrade() -> None:
    op.drop_column("people", "is_active")
