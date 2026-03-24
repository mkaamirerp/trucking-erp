"""Create email_threads and email_messages foundations.

Revision ID: p1q2r3s4t5u6
Revises: o7p8q9r0s1t2
Create Date: 2026-03-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p1q2r3s4t5u6"
down_revision = "o7p8q9r0s1t2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_thread_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("participants_json", sa.JSON(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unread_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("linked_load_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["linked_load_id"], ["loads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "external_thread_id",
            name="uq_email_threads_tenant_provider_external_thread_id",
        ),
    )
    op.create_index("ix_email_threads_tenant_id", "email_threads", ["tenant_id"], unique=False)

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=False),
        sa.Column("external_thread_id", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=True),
        sa.Column("from_email", sa.String(length=320), nullable=True),
        sa.Column("to_json", sa.JSON(), nullable=True),
        sa.Column("cc_json", sa.JSON(), nullable=True),
        sa.Column("bcc_json", sa.JSON(), nullable=True),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("extraction_status", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "external_message_id",
            name="uq_email_messages_tenant_provider_external_message_id",
        ),
    )
    op.create_index("ix_email_messages_tenant_id", "email_messages", ["tenant_id"], unique=False)
    op.create_index("ix_email_messages_thread_id", "email_messages", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_messages_thread_id", table_name="email_messages")
    op.drop_index("ix_email_messages_tenant_id", table_name="email_messages")
    op.drop_table("email_messages")

    op.drop_index("ix_email_threads_tenant_id", table_name="email_threads")
    op.drop_table("email_threads")
