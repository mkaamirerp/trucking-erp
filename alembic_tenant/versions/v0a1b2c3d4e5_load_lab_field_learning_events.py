"""load_lab_field_learning_events — tenant-private field learning (Load Lab).

Revision ID: v0a1b2c3d4e5
Revises: k9j8h7g6f5e4
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v0a1b2c3d4e5"
down_revision = "k9j8h7g6f5e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "load_lab_field_learning_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("field_path", sa.String(length=512), nullable=False),
        sa.Column("event_kind", sa.String(length=32), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("previous_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("response_contract", sa.String(length=32), nullable=True),
        sa.Column("correction_type", sa.String(length=32), nullable=True),
        sa.Column("event_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["load_lab_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_load_lab_field_learning_tenant", "load_lab_field_learning_events", ["tenant_id"])
    op.create_index("ix_load_lab_field_learning_run", "load_lab_field_learning_events", ["run_id"])
    op.create_index("ix_load_lab_field_learning_field_path", "load_lab_field_learning_events", ["field_path"])
    op.create_index("ix_load_lab_field_learning_event_kind", "load_lab_field_learning_events", ["event_kind"])


def downgrade() -> None:
    op.drop_index("ix_load_lab_field_learning_event_kind", table_name="load_lab_field_learning_events")
    op.drop_index("ix_load_lab_field_learning_field_path", table_name="load_lab_field_learning_events")
    op.drop_index("ix_load_lab_field_learning_run", table_name="load_lab_field_learning_events")
    op.drop_index("ix_load_lab_field_learning_tenant", table_name="load_lab_field_learning_events")
    op.drop_table("load_lab_field_learning_events")
