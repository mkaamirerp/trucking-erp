"""Load Lab semantic extract: metadata + validation on extraction runs.

Revision ID: m8n7o6p5q4r3
Revises: l9a8b7c6d5e4
Create Date: 2026-04-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "m8n7o6p5q4r3"
down_revision = "l9a8b7c6d5e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("semantic_model_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("semantic_prompt_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("semantic_schema_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("semantic_extract_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "load_lab_extraction_runs",
        sa.Column("semantic_validation_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("load_lab_extraction_runs", "semantic_validation_result")
    op.drop_column("load_lab_extraction_runs", "semantic_extract_status")
    op.drop_column("load_lab_extraction_runs", "semantic_schema_version")
    op.drop_column("load_lab_extraction_runs", "semantic_prompt_version")
    op.drop_column("load_lab_extraction_runs", "semantic_model_name")
