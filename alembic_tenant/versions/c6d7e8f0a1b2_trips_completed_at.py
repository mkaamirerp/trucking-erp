"""Trip container completed_at for Trip /complete closeout.

Revision ID: c6d7e8f0a1b2
Revises: b5c6d7e8f0a1
Create Date: 2026-08-12

trips.completed_at set on first successful POST /trips/{id}/complete only.
No backfill (no production API previously wrote Trip.status=completed).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c6d7e8f0a1b2"
down_revision = "b5c6d7e8f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trips", "completed_at")
