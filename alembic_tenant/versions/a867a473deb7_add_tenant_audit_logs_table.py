"""add tenant audit logs table

Revision ID: a867a473deb7
Revises: 8c84780c154b
Create Date: 2026-02-01

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a867a473deb7"
down_revision = "8c84780c154b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=128), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_tenant_audit_logs_tenant_id", "tenant_audit_logs", ["tenant_id"])
    op.create_index("ix_tenant_audit_logs_action", "tenant_audit_logs", ["action"])
    op.create_index("ix_tenant_audit_logs_object", "tenant_audit_logs", ["object_type", "object_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_audit_logs_object", table_name="tenant_audit_logs")
    op.drop_index("ix_tenant_audit_logs_action", table_name="tenant_audit_logs")
    op.drop_index("ix_tenant_audit_logs_tenant_id", table_name="tenant_audit_logs")
    op.drop_table("tenant_audit_logs")
