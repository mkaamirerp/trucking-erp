"""Load Lab: extraction runs and promote audit tables.

Revision ID: l9a8b7c6d5e4
Revises: t2u3v4w5x6y7
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "l9a8b7c6d5e4"
down_revision = "t2u3v4w5x6y7"
branch_labels = None
depends_on = None

RUN_STATUSES = (
    "uploaded",
    "deduped",
    "text_extracted",
    "ocr_required",
    "ocr_complete",
    "classified",
    "mapped",
    "validated",
    "review_required",
    "promoted",
    "rejected",
    "failed",
)

EXTRACTION_PATHS = ("digital", "ocr_required", "ocr_complete")


def upgrade() -> None:
    status_ck = "ck_load_lab_runs_status"
    path_ck = "ck_load_lab_runs_extraction_path"
    promote_target_ck = "ck_load_lab_promote_target_type"
    promote_out_ck = "ck_load_lab_promote_outcome"

    op.create_table(
        "load_lab_extraction_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source_route", sa.String(length=128), nullable=False, server_default="load_lab"),
        sa.Column("created_by_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extraction_path", sa.String(length=32), nullable=True),
        sa.Column("dedupe_prior_run_id", sa.BigInteger(), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("ocr_engine_version", sa.String(length=64), nullable=True),
        sa.Column("normalizer_version", sa.String(length=64), nullable=False),
        sa.Column("classification_label", sa.String(length=64), nullable=True),
        sa.Column("relevance", sa.String(length=32), nullable=True),
        sa.Column("normalized_package", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parse_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ai_model_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("field_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("contradictions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pipeline_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dedupe_prior_run_id"],
            ["load_lab_extraction_runs.id"],
            name="fk_load_lab_runs_dedupe_prior_run",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"status in ({','.join(repr(s) for s in RUN_STATUSES)})",
            name=status_ck,
        ),
        sa.CheckConstraint(
            f"extraction_path is null or extraction_path in ({','.join(repr(p) for p in EXTRACTION_PATHS)})",
            name=path_ck,
        ),
    )
    op.create_index("ix_load_lab_runs_tenant_created", "load_lab_extraction_runs", ["tenant_id", sa.text("id DESC")])
    op.create_index("ix_load_lab_runs_tenant_hash", "load_lab_extraction_runs", ["tenant_id", "file_sha256"])

    op.create_table(
        "load_lab_promote_audits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("operator_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("promote_target_type", sa.String(length=32), nullable=False),
        sa.Column("target_load_id", sa.BigInteger(), nullable=True),
        sa.Column("fields_accepted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fields_blocked", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("overwrite_decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("outcome_detail", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["load_lab_extraction_runs.id"],
            name="fk_load_lab_promote_run",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "promote_target_type in ('create_draft','update_existing')",
            name=promote_target_ck,
        ),
        sa.CheckConstraint(
            "outcome in ('success','failed')",
            name=promote_out_ck,
        ),
    )
    op.create_index("ix_load_lab_promote_tenant_run", "load_lab_promote_audits", ["tenant_id", "run_id"])
    op.create_index("ix_load_lab_promote_tenant_created", "load_lab_promote_audits", ["tenant_id", sa.text("id DESC")])


def downgrade() -> None:
    op.drop_index("ix_load_lab_promote_tenant_created", table_name="load_lab_promote_audits")
    op.drop_index("ix_load_lab_promote_tenant_run", table_name="load_lab_promote_audits")
    op.drop_table("load_lab_promote_audits")
    op.drop_index("ix_load_lab_runs_tenant_hash", table_name="load_lab_extraction_runs")
    op.drop_index("ix_load_lab_runs_tenant_created", table_name="load_lab_extraction_runs")
    op.drop_table("load_lab_extraction_runs")
