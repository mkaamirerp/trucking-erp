"""Generic extraction_field_learning_events; migrate from load_lab-only table.

Revision ID: w1a2b3c4d5e6
Revises: v0a1b2c3d4e5
Create Date: 2026-04-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "w1a2b3c4d5e6"
down_revision = "v0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_field_learning_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("origin_type", sa.String(length=32), nullable=False),
        sa.Column("origin_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("field_path", sa.String(length=512), nullable=False),
        sa.Column("event_kind", sa.String(length=32), nullable=False),
        sa.Column("proposed_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("final_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("previous_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correction_type", sa.String(length=32), nullable=True),
        sa.Column("source_label", sa.String(length=256), nullable=True),
        sa.Column("source_section", sa.String(length=256), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("response_contract", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=128), nullable=True),
        sa.Column("event_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_efl_tenant", "extraction_field_learning_events", ["tenant_id"])
    op.create_index("ix_efl_origin", "extraction_field_learning_events", ["origin_type", "origin_id"])
    op.create_index("ix_efl_field_path", "extraction_field_learning_events", ["field_path"])
    op.create_index("ix_efl_event_kind", "extraction_field_learning_events", ["event_kind"])
    op.create_index("ix_efl_created", "extraction_field_learning_events", ["created_at"])

    bind = op.get_bind()
    r = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'load_lab_field_learning_events')"
        )
    )
    if r.scalar():
        op.execute(
            sa.text(
                """
                INSERT INTO extraction_field_learning_events (
                    tenant_id, origin_type, origin_id, created_at, field_path, event_kind,
                    proposed_value_json, final_value_json, previous_value_json,
                    source_text, source_page, response_contract, correction_type, event_meta,
                    parser_version, source_label, source_section, actor_user_id
                )
                SELECT
                    tenant_id,
                    'load_lab_run',
                    run_id,
                    created_at,
                    field_path,
                    event_kind,
                    CASE WHEN event_kind = 'ai_proposed' THEN value_json ELSE NULL END,
                    CASE WHEN event_kind = 'ai_proposed' THEN NULL ELSE value_json END,
                    previous_value_json,
                    source_text,
                    source_page,
                    response_contract,
                    correction_type,
                    event_meta,
                    NULL,
                    NULL,
                    NULL,
                    created_by_platform_user_id
                FROM load_lab_field_learning_events
                """
            )
        )
        op.drop_index("ix_load_lab_field_learning_event_kind", table_name="load_lab_field_learning_events")
        op.drop_index("ix_load_lab_field_learning_field_path", table_name="load_lab_field_learning_events")
        op.drop_index("ix_load_lab_field_learning_run", table_name="load_lab_field_learning_events")
        op.drop_index("ix_load_lab_field_learning_tenant", table_name="load_lab_field_learning_events")
        op.drop_table("load_lab_field_learning_events")


def downgrade() -> None:
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
    op.execute(
        sa.text(
            """
            INSERT INTO load_lab_field_learning_events (
                tenant_id, run_id, created_at, created_by_platform_user_id, field_path, event_kind,
                value_json, previous_value_json, source_text, source_page, response_contract, correction_type, event_meta
            )
            SELECT
                tenant_id, origin_id, created_at, actor_user_id, field_path, event_kind,
                COALESCE(proposed_value_json, final_value_json), previous_value_json,
                source_text, source_page,
                LEFT(COALESCE(response_contract, ''), 32),
                correction_type, event_meta
            FROM extraction_field_learning_events
            WHERE origin_type = 'load_lab_run'
            """
        )
    )
    op.drop_index("ix_efl_created", table_name="extraction_field_learning_events")
    op.drop_index("ix_efl_event_kind", table_name="extraction_field_learning_events")
    op.drop_index("ix_efl_field_path", table_name="extraction_field_learning_events")
    op.drop_index("ix_efl_origin", table_name="extraction_field_learning_events")
    op.drop_index("ix_efl_tenant", table_name="extraction_field_learning_events")
    op.drop_table("extraction_field_learning_events")
