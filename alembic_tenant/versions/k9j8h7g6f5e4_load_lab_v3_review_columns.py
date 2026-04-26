"""Load Lab v3: confidence + review status columns on extraction runs.

Revision ID: k9j8h7g6f5e4
Revises: m8n7o6p5q4r3
Create Date: 2026-04-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "k9j8h7g6f5e4"
down_revision = "m8n7o6p5q4r3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("lab_confidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("lab_review_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("lab_review_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("load_lab_extraction_runs", "lab_review_summary")
    op.drop_column("load_lab_extraction_runs", "lab_review_status")
    op.drop_column("load_lab_extraction_runs", "lab_confidence")
