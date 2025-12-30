"""Create platform_tenants and platform_audit_log tables

Revision ID: 0005_platform_registry
Revises: c8a3d0b9c777
Create Date: 2025-01-01 00:00:00.000001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_platform_registry"
down_revision: Union[str, Sequence[str], None] = "c8a3d0b9c777"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'active'")),
        sa.Column("plan", sa.String(length=50), nullable=True),
        sa.Column("modules_enabled", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("privacy_mode", sa.String(length=30), nullable=False, server_default=sa.text("'standard'")),
        sa.Column("audit_visibility_mode", sa.String(length=30), nullable=False, server_default=sa.text("'tenant_support'")),
        sa.Column("email_provider_type", sa.String(length=50), nullable=False, server_default=sa.text("'platform_smtp'")),
        sa.Column("email_last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_last_test_result", sa.String(length=255), nullable=True),
        sa.Column("db_host", sa.String(length=255), nullable=True),
        sa.Column("db_port", sa.Integer(), nullable=True),
        sa.Column("db_name", sa.String(length=255), nullable=True),
        sa.Column("db_user", sa.String(length=255), nullable=True),
        sa.Column("db_password_encrypted", sa.String(length=1024), nullable=True),
        sa.Column("ssl_mode", sa.String(length=30), nullable=True),
        sa.Column("provisioning_mode", sa.String(length=20), nullable=True),
        sa.Column("db_status", sa.String(length=20), nullable=True),
        sa.Column("db_last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_platform_tenants_slug"),
    )

    op.create_table(
        "platform_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_audit_log")
    op.drop_table("platform_tenants")
