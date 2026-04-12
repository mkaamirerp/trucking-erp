"""Add zip_code alongside postal fields (people, person_applications, driver_onboarding_submissions).

Revision ID: g0a1b2c3d4e5
Revises: d0e1f2a3b4c5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g0a1b2c3d4e5"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("people", sa.Column("zip_code", sa.String(length=20), nullable=True))
    op.add_column(
        "person_applications",
        sa.Column("zip_code", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "driver_onboarding_submissions",
        sa.Column("zip_code", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("driver_onboarding_submissions", "zip_code")
    op.drop_column("person_applications", "zip_code")
    op.drop_column("people", "zip_code")
