"""Load workspace draft + commercial evidence foundation (DW-1).

Revision ID: dw1f2a3b4c5d6
Revises: dw0_merge_tenant_heads_a1b2_x5
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dw1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "dw0_merge_tenant_heads_a1b2_x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "load_workspace_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("concurrency_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("draft_schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "draft_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("source_channel", sa.String(length=32), nullable=False),
        sa.Column("created_by_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("email_thread_id", sa.Integer(), nullable=True),
        sa.Column("pdf_storage_key", sa.Text(), nullable=True),
        sa.Column(
            "pdf_retention_class",
            sa.String(length=16),
            server_default="workspace_ttl",
            nullable=False,
        ),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("pdf_filename", sa.Text(), nullable=True),
        sa.Column("pdf_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("pdf_upload_state", sa.String(length=16), server_default="idle", nullable=False),
        sa.Column("pdf_pending_storage_key", sa.Text(), nullable=True),
        sa.Column("pdf_upload_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pdf_upload_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_parse_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("accepted_parse_schema_version", sa.String(length=64), nullable=True),
        sa.Column("accepted_parse_pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_load_id", sa.Integer(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promotion_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discard_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["email_thread_id"], ["email_threads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_load_workspace_drafts_tenant_id_id"),
        sa.CheckConstraint(
            "status in ('draft', 'promoted', 'discarded', 'expired')",
            name="ck_load_workspace_drafts_status",
        ),
        sa.CheckConstraint(
            "pdf_upload_state in ('idle', 'uploading', 'ready')",
            name="ck_load_workspace_drafts_pdf_upload_state",
        ),
        sa.CheckConstraint(
            "pdf_retention_class in ('workspace_ttl', 'commercial_permanent')",
            name="ck_load_workspace_drafts_pdf_retention_class",
        ),
        sa.CheckConstraint(
            "(status = 'promoted' AND promoted_load_id IS NOT NULL) "
            "OR (status != 'promoted' AND promoted_load_id IS NULL)",
            name="ck_load_workspace_drafts_promoted_load_id_status",
        ),
    )
    op.create_foreign_key(
        "fk_load_workspace_drafts_promoted_load_tenant",
        "load_workspace_drafts",
        "loads",
        ["tenant_id", "promoted_load_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_load_workspace_drafts_tenant_id",
        "load_workspace_drafts",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_load_workspace_drafts_tenant_status_expires",
        "load_workspace_drafts",
        ["tenant_id", "status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_load_workspace_drafts_tenant_creator_updated",
        "load_workspace_drafts",
        ["tenant_id", "created_by_platform_user_id", sa.text("updated_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_load_workspace_drafts_tenant_email_thread",
        "load_workspace_drafts",
        ["tenant_id", "email_thread_id"],
        unique=False,
        postgresql_where=sa.text("email_thread_id IS NOT NULL"),
    )
    op.create_index(
        "uq_load_workspace_drafts_tenant_promoted_load_id",
        "load_workspace_drafts",
        ["tenant_id", "promoted_load_id"],
        unique=True,
        postgresql_where=sa.text("promoted_load_id IS NOT NULL"),
    )
    op.create_index(
        "uq_load_workspace_drafts_tenant_promotion_idempotency_key",
        "load_workspace_drafts",
        ["tenant_id", "promotion_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("promotion_idempotency_key IS NOT NULL"),
    )

    op.add_column(
        "loads",
        sa.Column("promotion_origin_workspace_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_loads_promotion_origin_workspace_draft",
        "loads",
        "load_workspace_drafts",
        ["promotion_origin_workspace_draft_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_loads_tenant_promotion_origin_draft",
        "loads",
        ["tenant_id", "promotion_origin_workspace_draft_id"],
        unique=True,
        postgresql_where=sa.text("promotion_origin_workspace_draft_id IS NOT NULL"),
    )

    op.create_table(
        "load_commercial_evidence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column(
            "evidence_kind",
            sa.String(length=32),
            server_default="rate_confirmation_pdf",
            nullable=False,
        ),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column(
            "retention_class",
            sa.String(length=32),
            server_default="commercial_permanent",
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("accepted_parse_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parse_schema_version", sa.String(length=64), nullable=True),
        sa.Column("workspace_draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promoted_by_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_commercial_evidence_load_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_draft_id"],
            ["load_workspace_drafts.tenant_id", "load_workspace_drafts.id"],
            name="fk_load_commercial_evidence_workspace_draft_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workspace_draft_id", name="uq_load_commercial_evidence_tenant_draft"),
        sa.UniqueConstraint(
            "tenant_id",
            "load_id",
            "evidence_kind",
            name="uq_load_commercial_evidence_tenant_load_kind",
        ),
        sa.CheckConstraint(
            "retention_class = 'commercial_permanent'",
            name="ck_load_commercial_evidence_retention_class",
        ),
    )
    op.create_index(
        "ix_load_commercial_evidence_tenant_id",
        "load_commercial_evidence",
        ["tenant_id"],
        unique=False,
    )

    op.add_column(
        "email_threads",
        sa.Column("workspace_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_email_threads_workspace_draft",
        "email_threads",
        "load_workspace_drafts",
        ["workspace_draft_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_email_threads_tenant_workspace_draft",
        "email_threads",
        ["tenant_id", "workspace_draft_id"],
        unique=False,
        postgresql_where=sa.text("workspace_draft_id IS NOT NULL"),
    )

    op.add_column(
        "email_intake_qr_extractions",
        sa.Column("workspace_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_email_intake_qr_extractions_workspace_draft",
        "email_intake_qr_extractions",
        "load_workspace_drafts",
        ["workspace_draft_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_email_intake_qr_extractions_workspace_draft",
        "email_intake_qr_extractions",
        type_="foreignkey",
    )
    op.drop_column("email_intake_qr_extractions", "workspace_draft_id")

    op.drop_index("ix_email_threads_tenant_workspace_draft", table_name="email_threads")
    op.drop_constraint("fk_email_threads_workspace_draft", "email_threads", type_="foreignkey")
    op.drop_column("email_threads", "workspace_draft_id")

    op.drop_index("ix_load_commercial_evidence_tenant_id", table_name="load_commercial_evidence")
    op.drop_table("load_commercial_evidence")

    op.drop_index("uq_loads_tenant_promotion_origin_draft", table_name="loads")
    op.drop_constraint("fk_loads_promotion_origin_workspace_draft", "loads", type_="foreignkey")
    op.drop_column("loads", "promotion_origin_workspace_draft_id")

    op.drop_index(
        "uq_load_workspace_drafts_tenant_promotion_idempotency_key",
        table_name="load_workspace_drafts",
    )
    op.drop_index("uq_load_workspace_drafts_tenant_promoted_load_id", table_name="load_workspace_drafts")
    op.drop_index("ix_load_workspace_drafts_tenant_email_thread", table_name="load_workspace_drafts")
    op.drop_index("ix_load_workspace_drafts_tenant_creator_updated", table_name="load_workspace_drafts")
    op.drop_index("ix_load_workspace_drafts_tenant_status_expires", table_name="load_workspace_drafts")
    op.drop_index("ix_load_workspace_drafts_tenant_id", table_name="load_workspace_drafts")
    op.drop_constraint(
        "fk_load_workspace_drafts_promoted_load_tenant",
        "load_workspace_drafts",
        type_="foreignkey",
    )
    op.drop_table("load_workspace_drafts")
