"""Merge tenant heads (guardrail + idempotent composite FK)

Revision ID: f9a0b1c2d3e4
Revises: c6d7e8f9a0b1, d7e8f9a0b1c2
Create Date: 2026-02-23

Merge only. No schema changes.
Unifies heads so upgrade path is deterministic.
"""

from __future__ import annotations

from alembic import op

revision = "f9a0b1c2d3e4"
down_revision = ("c6d7e8f9a0b1", "d7e8f9a0b1c2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
