"""Create email_message_attachments foundation table.

Revision ID: u7v8w9x0y1z2
Revises: p1q2r3s4t5u6
Create Date: 2026-03-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u7v8w9x0y1z2"
down_revision = "p1q2r3s4t5u6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_message_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_attachment_id", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("is_inline", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("download_status", sa.String(length=30), server_default="metadata_only", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["email_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "message_id",
            "external_attachment_id",
            name="uq_email_message_attachments_tenant_provider_message_attachment",
        ),
    )
    op.create_index("ix_email_message_attachments_tenant_id", "email_message_attachments", ["tenant_id"], unique=False)
    op.create_index("ix_email_message_attachments_message_id", "email_message_attachments", ["message_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_message_attachments_message_id", table_name="email_message_attachments")
    op.drop_index("ix_email_message_attachments_tenant_id", table_name="email_message_attachments")
    op.drop_table("email_message_attachments")
