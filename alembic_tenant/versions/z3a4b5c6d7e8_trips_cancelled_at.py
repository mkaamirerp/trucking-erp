"""Phase 3D: trips.cancelled_at for manual Trip cancel audit.

Revision ID: z3a4b5c6d7e8
Revises: y1a2b3c4d5e4
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "z3a4b5c6d7e8"
down_revision = "y1a2b3c4d5e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "cancelled_at")
