"""Decision 10 / COMMIT 4a: trips scheduling bounds (nullable).

Revision ID: a4b5c6d7e8f0
Revises: z3a4b5c6d7e8
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a4b5c6d7e8f0"
down_revision = "z3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "trips", sa.Column("expected_completion_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("trips", "expected_completion_at")
    op.drop_column("trips", "planned_start_at")
