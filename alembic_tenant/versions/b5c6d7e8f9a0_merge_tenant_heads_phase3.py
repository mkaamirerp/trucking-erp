"""Merge tenant heads (phase3 composite FKs branch)

Revision ID: b5c6d7e8f9a0
Revises: f3c4d5e6f7a8, a4b5c6d7e8f9
Create Date: 2026-02-23

Merge only. No schema changes.
Makes Alembic graph single-head so upgrade path is deterministic.
"""

from __future__ import annotations

from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = ("f3c4d5e6f7a8", "a4b5c6d7e8f9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
