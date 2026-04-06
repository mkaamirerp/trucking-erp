"""Email intake: structured QR extractions from broker documents (tenant-scoped).

Revision ID: f8e9d0c1b2a3
Revises: d5e6f7a8b9c0

Includes: source type, page_number, normalized_value, dedupe partial uniques.

Upgrade is idempotent: fresh DB creates the full table; if an older draft of this table
already exists, missing columns and indexes are added.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "f8e9d0c1b2a3"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def _index_names(inspector: Inspector) -> set[str]:
    return {i["name"] for i in inspector.get_indexes("email_intake_qr_extractions")}


def _ensure_columns_and_indexes() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    cols = {c["name"] for c in inspector.get_columns("email_intake_qr_extractions")}
    if "extracted_from_source_type" not in cols:
        op.add_column(
            "email_intake_qr_extractions",
            sa.Column(
                "extracted_from_source_type",
                sa.String(length=32),
                nullable=False,
                server_default="other",
            ),
        )
        op.alter_column("email_intake_qr_extractions", "extracted_from_source_type", server_default=None)
    if "page_number" not in cols:
        op.add_column("email_intake_qr_extractions", sa.Column("page_number", sa.Integer(), nullable=True))
    if "normalized_value" not in cols:
        op.add_column("email_intake_qr_extractions", sa.Column("normalized_value", sa.Text(), nullable=True))

    inspector = Inspector.from_engine(bind)
    ix = _index_names(inspector)

    if "ix_email_intake_qr_extractions_tenant_id" not in ix:
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_id", "email_intake_qr_extractions", ["tenant_id"], unique=False
        )
    if "ix_email_intake_qr_extractions_thread_id" not in ix:
        op.create_index(
            "ix_email_intake_qr_extractions_thread_id", "email_intake_qr_extractions", ["thread_id"], unique=False
        )
    if "ix_email_intake_qr_extractions_message_id" not in ix:
        op.create_index(
            "ix_email_intake_qr_extractions_message_id", "email_intake_qr_extractions", ["message_id"], unique=False
        )
    if "ix_email_intake_qr_extractions_tenant_attachment" not in ix:
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_attachment",
            "email_intake_qr_extractions",
            ["tenant_id", "attachment_id"],
            unique=False,
        )
    if "ix_email_intake_qr_extractions_tenant_raw_value" not in ix:
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_raw_value",
            "email_intake_qr_extractions",
            ["tenant_id", "raw_value"],
            unique=False,
        )
    if "ix_email_intake_qr_extractions_tenant_normalized_value" not in ix:
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_normalized_value",
            "email_intake_qr_extractions",
            ["tenant_id", "normalized_value"],
            unique=False,
            postgresql_where=sa.text("normalized_value IS NOT NULL"),
        )
    if "uq_email_intake_qr_tenant_attachment_raw" not in ix:
        op.create_index(
            "uq_email_intake_qr_tenant_attachment_raw",
            "email_intake_qr_extractions",
            ["tenant_id", "attachment_id", "raw_value"],
            unique=True,
            postgresql_where=sa.text("attachment_id IS NOT NULL"),
        )
    if "uq_email_intake_qr_tenant_message_raw" not in ix:
        op.create_index(
            "uq_email_intake_qr_tenant_message_raw",
            "email_intake_qr_extractions",
            ["tenant_id", "message_id", "raw_value"],
            unique=True,
            postgresql_where=sa.text("attachment_id IS NULL"),
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()
    if "email_intake_qr_extractions" not in tables:
        op.create_table(
            "email_intake_qr_extractions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("attachment_id", sa.Integer(), nullable=True),
            sa.Column("raw_value", sa.Text(), nullable=False),
            sa.Column("normalized_value", sa.Text(), nullable=True),
            sa.Column(
                "extracted_from_source_type",
                sa.String(length=32),
                nullable=False,
                server_default="other",
            ),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("format_hint", sa.String(length=64), nullable=True),
            sa.Column("decoder_backend", sa.String(length=64), nullable=True),
            sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="ok"),
            sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("linked_broker_id", sa.Integer(), nullable=True),
            sa.Column("linked_load_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["attachment_id"], ["email_message_attachments.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_broker_id"], ["brokers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_load_id"], ["loads.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["message_id"], ["email_messages.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_id", "email_intake_qr_extractions", ["tenant_id"], unique=False
        )
        op.create_index(
            "ix_email_intake_qr_extractions_thread_id", "email_intake_qr_extractions", ["thread_id"], unique=False
        )
        op.create_index(
            "ix_email_intake_qr_extractions_message_id", "email_intake_qr_extractions", ["message_id"], unique=False
        )
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_attachment",
            "email_intake_qr_extractions",
            ["tenant_id", "attachment_id"],
            unique=False,
        )
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_raw_value",
            "email_intake_qr_extractions",
            ["tenant_id", "raw_value"],
            unique=False,
        )
        op.create_index(
            "ix_email_intake_qr_extractions_tenant_normalized_value",
            "email_intake_qr_extractions",
            ["tenant_id", "normalized_value"],
            unique=False,
            postgresql_where=sa.text("normalized_value IS NOT NULL"),
        )
        op.create_index(
            "uq_email_intake_qr_tenant_attachment_raw",
            "email_intake_qr_extractions",
            ["tenant_id", "attachment_id", "raw_value"],
            unique=True,
            postgresql_where=sa.text("attachment_id IS NOT NULL"),
        )
        op.create_index(
            "uq_email_intake_qr_tenant_message_raw",
            "email_intake_qr_extractions",
            ["tenant_id", "message_id", "raw_value"],
            unique=True,
            postgresql_where=sa.text("attachment_id IS NULL"),
        )
    else:
        _ensure_columns_and_indexes()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if "email_intake_qr_extractions" not in inspector.get_table_names():
        return
    op.drop_index("uq_email_intake_qr_tenant_message_raw", table_name="email_intake_qr_extractions")
    op.drop_index("uq_email_intake_qr_tenant_attachment_raw", table_name="email_intake_qr_extractions")
    op.drop_index("ix_email_intake_qr_extractions_tenant_normalized_value", table_name="email_intake_qr_extractions")
    op.drop_index("ix_email_intake_qr_extractions_tenant_raw_value", table_name="email_intake_qr_extractions")
    op.drop_index("ix_email_intake_qr_extractions_tenant_attachment", table_name="email_intake_qr_extractions")
    op.drop_index("ix_email_intake_qr_extractions_message_id", table_name="email_intake_qr_extractions")
    op.drop_index("ix_email_intake_qr_extractions_thread_id", table_name="email_intake_qr_extractions")
    op.drop_index("ix_email_intake_qr_extractions_tenant_id", table_name="email_intake_qr_extractions")
    op.drop_table("email_intake_qr_extractions")
